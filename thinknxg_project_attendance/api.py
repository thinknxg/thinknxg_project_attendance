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
