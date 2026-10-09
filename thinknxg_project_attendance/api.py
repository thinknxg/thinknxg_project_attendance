import frappe
from frappe import _
from frappe.utils import cint

from thinknxg_project_attendance.project_attendance.doctype.bulk_attendance_record.bulk_attendance_record import (
    fill_days,
)
from thinknxg_project_attendance.utils.common import get_month_range, get_settings


@frappe.whitelist()
def create_bulk_records(
    company,
    posting_month,
    posting_year,
    common_project=None,
    grade=None,
    department=None,
    project_change_allowed=0,
    common_shift=None,
    shift_change_allowed=0,
):
    """Create draft Bulk Attendance Records for every active employee matching the filters."""
    frappe.has_permission("Bulk Attendance Record", "create", throw=True)
    if not common_project and not cint(project_change_allowed):
        frappe.throw(_("Select a Common Project or allow project change."))

    first, last = get_month_range(posting_month, posting_year)
    filters = {"status": "Active", "company": company, "date_of_joining": ["<=", last]}
    if grade:
        filters["grade"] = grade
    if department:
        filters["department"] = department

    employees = frappe.get_list("Employee", filters=filters, pluck="name", order_by="name", limit_page_length=0)
    settings = get_settings()
    created, skipped = [], []

    for employee in employees:
        if frappe.db.exists(
            "Bulk Attendance Record",
            {
                "employee": employee,
                "docstatus": ["<", 2],
                "from_date": ["<=", last],
                "to_date": [">=", first],
            },
        ):
            skipped.append(employee)
            continue

        doc = frappe.new_doc("Bulk Attendance Record")
        doc.update(
            {
                "company": company,
                "posting_month": posting_month,
                "posting_year": str(cint(posting_year)),
                "from_date": first,
                "to_date": last,
                "employee": employee,
                "grade": grade,
                "common_project": common_project,
                "project_change_allowed": cint(project_change_allowed),
                # empty = each employee's own Default Shift
                "common_shift": common_shift,
                "shift_change_allowed": cint(shift_change_allowed),
            }
        )
        doc._settings = settings
        doc.validate_employee()
        fill_days(doc, settings, doc._employee)
        if not doc.details:
            skipped.append(employee)
            continue
        doc.insert()
        created.append(doc.name)

    return {"created": created, "skipped": skipped}


@frappe.whitelist()
def project_checkin(log_type, project=None, device_id=None, latitude=None, longitude=None, employee=None):
    """Create an Employee Checkin with a project (mobile apps, kiosks, integrations).

    Without `employee` the checkin is for the employee linked to the logged-in user.
    """
    from frappe.utils import now_datetime

    if log_type not in ("IN", "OUT"):
        frappe.throw(_("Log Type must be IN or OUT."))

    own = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
    if employee and employee != own:
        frappe.has_permission("Employee Checkin", "create", throw=True)
    employee = employee or own
    if not employee:
        frappe.throw(_("No active Employee is linked to user {0}.").format(frappe.session.user))

    checkin = frappe.new_doc("Employee Checkin")
    checkin.update(
        {
            "employee": employee,
            "log_type": log_type,
            "time": now_datetime(),
            "device_id": device_id,
            "nxg_project": project,
        }
    )
    if latitude is not None and longitude is not None:
        checkin.latitude = latitude
        checkin.longitude = longitude
    checkin.flags.ignore_permissions = bool(employee == own)
    checkin.insert()
    return {"name": checkin.name, "time": checkin.time, "project": checkin.get("nxg_project")}


@frappe.whitelist()
def get_employee_defaults(employee, on_date=None):
    """Default shift and main project of an employee, to pre-fill a Bulk Attendance Record."""
    from frappe.utils import getdate, nowdate

    from thinknxg_project_attendance.utils.ledger import ProjectResolver

    frappe.has_permission("Bulk Attendance Record", "read", throw=True)
    on_date = getdate(on_date or nowdate())
    resolver = ProjectResolver()
    rows = resolver.assignments(employee, on_date)
    project = None
    if rows:
        project = max(rows, key=lambda r: (cint(r.is_primary), r.allocation_percent or 0)).project
    else:
        project = resolver.defaults(employee)[0]
    return {
        "default_shift": frappe.db.get_value("Employee", employee, "default_shift"),
        "project": project,
    }
