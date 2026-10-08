import calendar

import frappe
from frappe.utils import cint, flt, getdate

from thinknxg_project_attendance.utils.common import (
    METHOD_FIXED,
    METHOD_HOURLY,
    get_salary_assignment,
    get_settings,
)


def get_overtime_rate(employee, on_date, is_holiday=False, grade=None, settings=None, cache=None):
    """Return the overtime rate per hour for an employee on a date.

    The rate is expressed in the currency of the employee's Salary Structure Assignment
    (the same currency the Additional Salary and the Salary Slip use).
    Returns 0 when the rate cannot be determined.
    """
    settings = settings or get_settings()
    cache = cache if cache is not None else {}
    method = settings.overtime_calculation_method

    if method == METHOD_FIXED:
        return flt(settings.fixed_overtime_rate)

    if method == METHOD_HOURLY:
        key = ("hourly", employee)
        if key not in cache:
            rate = flt(frappe.db.get_value("Employee", employee, "nxg_overtime_hourly_rate"))
            if not rate:
                grade = grade or frappe.db.get_value("Employee", employee, "grade")
                if grade:
                    rate = flt(frappe.db.get_value("Employee Grade", grade, "nxg_overtime_hourly_rate"))
            cache[key] = rate
        return cache[key]

    # Basic / Working Hours x Multiplier
    on_date = getdate(on_date)
    key = ("base", employee, on_date.year, on_date.month)
    if key not in cache:
        month_end = getdate(
            f"{on_date.year}-{on_date.month:02d}-{calendar.monthrange(on_date.year, on_date.month)[1]:02d}"
        )
        assignment = get_salary_assignment(employee, month_end)
        cache[key] = flt(assignment.base) if assignment else 0.0
    base = cache[key]
    if not base:
        return 0.0

    divisor_days = cint(settings.monthly_divisor_days) or calendar.monthrange(on_date.year, on_date.month)[1]
    normal_hours = flt(settings.normal_working_hours) or 8.0
    multiplier = flt(settings.overtime_multiplier) or 1.0
    if is_holiday and flt(settings.holiday_overtime_multiplier):
        multiplier = flt(settings.holiday_overtime_multiplier)

    return base / divisor_days / normal_hours * multiplier


# ---------------------------------------------------------------------------- payroll posting
def _additional_salary_slip(additional_salary):
    """Salary Slip (draft or submitted) that already uses the Additional Salary."""
    return frappe.db.get_value(
        "Salary Detail",
        {"additional_salary": additional_salary, "parenttype": "Salary Slip", "docstatus": ["<", 2]},
        "parent",
    )


def release_additional_salary(additional_salary):
    """Cancel an overtime Additional Salary built from checkin overtime and free its overtime records,
    so that they are posted again with the next payroll run."""
    from frappe import _

    details = frappe.db.get_value(
        "Additional Salary", additional_salary, ["docstatus", "ref_doctype"], as_dict=True
    )
    if not details or details.ref_doctype == "Bulk Attendance Record":
        return

    slip = _additional_salary_slip(additional_salary)
    if slip:
        frappe.throw(
            _("Additional Salary {0} is already used in Salary Slip {1}. Cancel or delete the Salary Slip first.").format(
                additional_salary, slip
            ),
            title=_("Payroll Already Processed"),
        )

    frappe.db.set_value(
        "Project Overtime", {"additional_salary": additional_salary}, "additional_salary", None
    )
    if details.docstatus == 1:
        doc = frappe.get_doc("Additional Salary", additional_salary)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.cancel()


def post_overtime_additional_salary(employee, from_date, to_date, payroll_date=None, settings=None):
    """Create one Additional Salary for the approved, unposted checkin overtime of an employee.

    from_date None = everything up to to_date, so overtime approved after an earlier payroll run
    is paid with the next one. Pending and rejected overtime is never posted.
    Returns the Additional Salary name, or None when there is nothing to post.
    """
    from frappe import _

    from thinknxg_project_attendance.utils.common import currency_precision

    settings = settings or get_settings()
    if not cint(settings.create_additional_salary):
        return None

    records = frappe.get_all(
        "Project Overtime",
        filters={
            "employee": employee,
            "docstatus": 1,
            "approval_status": "Approved",
            "attendance_date": ["between", [from_date, to_date]] if from_date else ["<=", to_date],
            "additional_salary": ["is", "not set"],
            "salary_slip": ["is", "not set"],
            "bulk_attendance_record": ["is", "not set"],
        },
        fields=[
            "name",
            "attendance_date",
            "is_holiday",
            "overtime_hours",
            "approved_hours",
            "overtime_rate",
            "overtime_amount",
        ],
    )
    if not records:
        return None

    component = settings.overtime_salary_component
    if not component:
        frappe.throw(_("Set the Payroll Component for Overtime in Project Attendance Settings."))

    precision = currency_precision()
    cache = {}
    total = 0.0
    for record in records:
        if not flt(record.overtime_rate):
            # the rate was not available when the day was processed (e.g. salary assigned later)
            rate = flt(
                get_overtime_rate(
                    employee, record.attendance_date, is_holiday=cint(record.is_holiday), settings=settings, cache=cache
                ),
                6,
            )
            record.overtime_rate = rate
            record.overtime_amount = flt(rate * flt(record.approved_hours), precision)
            frappe.db.set_value(
                "Project Overtime",
                record.name,
                {"overtime_rate": rate, "overtime_amount": record.overtime_amount},
                update_modified=False,
            )
        total += flt(record.overtime_amount)

    total = flt(total, precision)
    if total <= 0:
        frappe.throw(
            _("The overtime rate of employee {0} is zero. Check the overtime method and the salary setup.").format(
                employee
            )
        )

    emp = frappe.db.get_value(
        "Employee", employee, ["employee_name", "department", "company", "relieving_date"], as_dict=True
    )
    payroll_date = getdate(payroll_date or to_date)
    if emp.relieving_date and payroll_date > getdate(emp.relieving_date):
        payroll_date = getdate(emp.relieving_date)

    assignment = get_salary_assignment(employee, payroll_date)
    currency = (assignment.currency if assignment else None) or frappe.get_cached_value(
        "Company", emp.company, "default_currency"
    )

    additional_salary = frappe.new_doc("Additional Salary")
    additional_salary.update(
        {
            "employee": employee,
            "employee_name": emp.employee_name,
            "department": emp.department,
            "company": emp.company,
            "salary_component": component,
            "amount": total,
            "currency": currency,
            "payroll_date": payroll_date,
            "is_recurring": 0,
            "overwrite_salary_structure_amount": 0,
            "nxg_project_overtime": 1,
        }
    )
    additional_salary.flags.ignore_permissions = True
    additional_salary.insert()
    additional_salary.submit()

    frappe.db.set_value(
        "Project Overtime",
        {"name": ["in", [r.name for r in records]]},
        "additional_salary",
        additional_salary.name,
    )
    return additional_salary.name


def post_overtime_for_employees(employees, from_date, to_date, payroll_date=None):
    """Post checkin overtime for many employees; one failing employee does not stop the others."""
    settings = get_settings()
    posted, failed = [], []
    mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        for employee in employees:
            try:
                frappe.db.savepoint("nxg_overtime_post")
                name = post_overtime_additional_salary(employee, from_date, to_date, payroll_date, settings)
                if name:
                    posted.append(name)
            except Exception as exc:
                frappe.db.rollback(save_point="nxg_overtime_post")
                failed.append((employee, str(exc)))
    finally:
        frappe.flags.mute_messages = mute
    return posted, failed


@frappe.whitelist()
def post_unpaid_overtime(from_date, to_date, company=None, employee=None, payroll_date=None):
    """Manual trigger (Project Overtime list): post approved, unposted checkin overtime to payroll."""
    from frappe import _

    frappe.only_for(("HR Manager", "HR User", "System Manager"))
    filters = {
        "docstatus": 1,
        "approval_status": "Approved",
        "attendance_date": ["between", [from_date, to_date]],
        "additional_salary": ["is", "not set"],
        "salary_slip": ["is", "not set"],
        "bulk_attendance_record": ["is", "not set"],
    }
    if company:
        filters["company"] = company
    if employee:
        filters["employee"] = employee
    employees = sorted(set(frappe.get_all("Project Overtime", filters=filters, pluck="employee")))
    posted, failed = post_overtime_for_employees(employees, from_date, to_date, payroll_date)
    if failed:
        frappe.msgprint(
            _("Overtime could not be posted for:")
            + "<ul>"
            + "".join(f"<li>{emp}: {frappe.utils.strip_html(msg)}</li>" for emp, msg in failed[:20])
            + "</ul>",
            title=_("Overtime Not Posted"),
            indicator="orange",
        )
    return {"posted": len(posted), "failed": len(failed)}
