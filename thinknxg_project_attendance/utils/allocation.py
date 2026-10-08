"""Project Salary Expense: allocate a submitted Salary Slip to the projects worked on."""
from collections import defaultdict

import frappe
from frappe.utils import cint, flt

from thinknxg_project_attendance.utils.common import (
    WORKED_STATUSES,
    currency_precision,
    distribute,
    get_payroll_cost_center,
    get_settings,
)

PSE = "Project Salary Expense"
PAL = "Project Attendance Ledger"
UNALLOCATED = ""  # key of hours without a project


def get_component_account(component, company, settings=None, cache=None):
    """Expense account of a salary component for the company (same lookup as the Payroll Entry)."""
    cache = cache if cache is not None else {}
    key = (component, company)
    if key not in cache:
        account = frappe.db.get_value(
            "Salary Component Account", {"parent": component, "company": company}, "account"
        )
        if not account:
            settings = settings or get_settings()
            fallback = settings.fallback_expense_account
            if fallback and frappe.db.get_value("Account", fallback, "company") == company:
                account = fallback
        cache[key] = account
    return cache[key]


def get_overtime_records(slip, settings=None):
    """Submitted Project Overtime paid through this slip.

    Overtime follows its Additional Salary (payroll date inside the slip period), exactly the way
    HRMS picks Additional Salary up - whether it came from a Bulk Attendance Record or from
    checkin overtime posted before the payroll run.
    """
    fields = [
        "name",
        "project",
        "overtime_hours",
        "approved_hours",
        "overtime_amount",
        "bulk_attendance_record",
        "additional_salary",
        "salary_slip",
    ]
    candidates = frappe.get_all(
        "Project Overtime",
        filters={"employee": slip.employee, "docstatus": 1, "additional_salary": ["is", "set"]},
        fields=fields,
    )
    candidates = [
        r for r in candidates if r.additional_salary and (not r.salary_slip or r.salary_slip == slip.name)
    ]
    if not candidates:
        return []

    in_period = set(
        frappe.get_all(
            "Additional Salary",
            filters={
                "name": ["in", list({r.additional_salary for r in candidates})],
                "docstatus": 1,
                "payroll_date": ["between", [slip.start_date, slip.end_date]],
            },
            pluck="name",
        )
    )
    return [r for r in candidates if r.additional_salary in in_period]


def create_project_salary_expenses(slip):
    if frappe.db.exists(PSE, {"salary_slip": slip.name}):
        return

    settings = get_settings()
    precision = currency_precision()
    exchange_rate = flt(slip.get("exchange_rate")) or 1.0
    ot_component = settings.overtime_salary_component
    basic_component = settings.basic_salary_component

    # 1. earnings of the slip that reach the books, in company currency
    regular = defaultdict(float)
    ot_amount = 0.0
    for row in slip.get("earnings") or []:
        if cint(row.get("statistical_component")):
            continue
        if cint(row.get("do_not_include_in_total")) and cint(row.get("do_not_include_in_accounts")):
            continue
        amount = flt(flt(row.amount) * exchange_rate, precision)
        if not amount:
            continue
        if ot_component and row.salary_component == ot_component:
            ot_amount += amount
        else:
            regular[row.salary_component] += amount

    # 2. allocation basis from the Project Attendance Ledger of the period (all sources)
    ledger = [
        row
        for row in frappe.get_all(
            PAL,
            filters={
                "employee": slip.employee,
                "attendance_date": ["between", [slip.start_date, slip.end_date]],
            },
            fields=[
                "name",
                "project",
                "attendance_status",
                "regular_hours",
                "day_fraction",
                "source",
                "bulk_attendance_record",
                "salary_slip",
            ],
        )
        if not row.salary_slip or row.salary_slip == slip.name
    ]
    method = settings.salary_allocation_method or "Working Days"
    basis = defaultdict(float)
    days = defaultdict(float)
    hours = defaultdict(float)
    sources = defaultdict(set)
    bulk_records = set()
    for row in ledger:
        if row.bulk_attendance_record:
            bulk_records.add(row.bulk_attendance_record)
        if row.attendance_status not in WORKED_STATUSES:
            continue
        key = row.project or UNALLOCATED
        fraction = flt(row.day_fraction)
        equivalent = fraction * (0.5 if row.attendance_status == "Half Day" else 1.0)
        days[key] += equivalent
        hours[key] += flt(row.regular_hours)
        sources[key].add(row.source)
        if method == "Working Hours":
            basis[key] += flt(row.regular_hours)
        elif method == "Attendance Days":
            basis[key] += equivalent
        else:
            basis[key] += fraction

    # 3. overtime is allocated directly to the project it was worked on
    overtime_records = get_overtime_records(slip, settings)
    ot_weights = defaultdict(float)
    ot_hours = defaultdict(float)
    for record in overtime_records:
        ot_weights[record.project or UNALLOCATED] += flt(record.overtime_amount)
        ot_hours[record.project or UNALLOCATED] += flt(record.approved_hours) or flt(record.overtime_hours)
        if record.bulk_attendance_record:
            bulk_records.add(record.bulk_attendance_record)

    total_basis = sum(basis.values())
    projects = sorted(set(basis) | set(ot_weights))
    if not projects:
        return

    account_cache = {}
    per_project = {p: frappe._dict(rows=[], salary=0.0, other=0.0, overtime=0.0) for p in projects}

    if total_basis:
        for component, amount in regular.items():
            account = get_component_account(component, slip.company, settings, account_cache)
            for project, share in distribute(amount, basis, precision).items():
                if not share:
                    continue
                bucket = per_project[project]
                bucket.rows.append(
                    {"salary_component": component, "expense_account": account, "is_overtime": 0, "amount": share}
                )
                if basic_component and component != basic_component:
                    bucket.other += share
                else:
                    bucket.salary += share

    if ot_amount:
        weights = ot_weights if sum(ot_weights.values()) > 0 else basis
        account = get_component_account(ot_component, slip.company, settings, account_cache)
        for project, share in distribute(ot_amount, weights, precision).items():
            if not share:
                continue
            bucket = per_project[project]
            bucket.rows.append(
                {"salary_component": ot_component, "expense_account": account, "is_overtime": 1, "amount": share}
            )
            bucket.overtime += share

    employee = frappe.db.get_value(
        "Employee", slip.employee, ["employee_name", "department", "grade"], as_dict=True
    ) or frappe._dict()
    source_cost_center = get_payroll_cost_center(slip.employee, slip.company, slip.get("payroll_entry"))

    for project in projects:
        bucket = per_project[project]
        if not bucket.rows:
            continue
        doc = frappe.new_doc(PSE)
        doc.update(
            {
                "employee": slip.employee,
                "employee_name": employee.employee_name or slip.employee_name,
                "department": employee.department,
                "grade": employee.grade,
                "project": project or None,
                "is_unallocated": 0 if project else 1,
                "attendance_sources": ", ".join(sorted(sources.get(project, []))),
                "posting_date": slip.posting_date,
                "from_date": slip.start_date,
                "to_date": slip.end_date,
                "company": slip.company,
                "salary_slip": slip.name,
                "payroll_entry": slip.get("payroll_entry"),
                "allocation_method": method,
                "basis_value": basis.get(project, 0),
                "total_basis": total_basis,
                "allocation_percent": (basis.get(project, 0) / total_basis * 100) if total_basis else 0,
                "days_worked": days.get(project, 0),
                "working_hours": hours.get(project, 0),
                "overtime_hours": ot_hours.get(project, 0),
                "salary_amount": flt(bucket.salary, precision),
                "other_earnings": flt(bucket.other, precision),
                "overtime_amount": flt(bucket.overtime, precision),
                "cost_center": (frappe.db.get_value("Project", project, "cost_center") if project else None)
                or source_cost_center,
                "source_cost_center": source_cost_center,
                # unallocated cost stays where payroll booked it: nothing to re-classify
                "gl_status": "Not Posted" if (project and slip.get("payroll_entry")) else "Not Required",
            }
        )
        for row in bucket.rows:
            doc.append("allocations", row)
        doc.flags.ignore_permissions = True
        doc.insert()

    if overtime_records and ot_amount:
        frappe.db.set_value(
            "Project Overtime",
            {"name": ["in", [r.name for r in overtime_records]]},
            {"salary_slip": slip.name, "status": "Paid"},
        )
    if bulk_records:
        frappe.db.set_value(
            "Bulk Attendance Record",
            {"name": ["in", list(bulk_records)], "docstatus": 1},
            "status",
            "Payroll Processed",
        )
    if ledger:
        # stamp the ledger: these days are costed and can no longer be reprocessed
        frappe.db.set_value(
            PAL, {"name": ["in", [row.name for row in ledger]]}, "salary_slip", slip.name, update_modified=False
        )


def remove_project_salary_expenses(slip):
    from thinknxg_project_attendance.utils.journal import reverse_journal

    expenses = frappe.get_all(PSE, filters={"salary_slip": slip.name}, fields=["name", "journal_entry"])
    for journal_entry in {e.journal_entry for e in expenses if e.journal_entry}:
        reverse_journal(journal_entry)
    for expense in expenses:
        frappe.delete_doc(PSE, expense.name, ignore_permissions=True, force=True)

    bulk_records = set(
        frappe.get_all("Project Overtime", filters={"salary_slip": slip.name}, pluck="bulk_attendance_record")
    )
    bulk_records |= set(frappe.get_all(PAL, filters={"salary_slip": slip.name}, pluck="bulk_attendance_record"))
    bulk_records.discard(None)
    bulk_records.discard("")

    frappe.db.set_value(PAL, {"salary_slip": slip.name}, "salary_slip", None, update_modified=False)
    frappe.db.set_value(
        "Project Overtime", {"salary_slip": slip.name}, {"salary_slip": None, "status": "Unpaid"}
    )
    if bulk_records:
        frappe.db.set_value(
            "Bulk Attendance Record",
            {"name": ["in", list(bulk_records)], "docstatus": 1, "status": "Payroll Processed"},
            "status",
            "Submitted",
        )
