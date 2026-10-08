"""v1.1: the Project Attendance Ledger becomes the costing source.

Write ledger rows for Bulk Attendance Records submitted with v1.0 and stamp the rows of periods
that are already costed, so that existing data keeps working with the new engine.
"""
import frappe

from thinknxg_project_attendance.utils.ledger import PAL, write_bulk_rows


def execute():
    records = frappe.get_all("Bulk Attendance Record", filters={"docstatus": 1}, pluck="name")
    for name in records:
        if frappe.db.exists(PAL, {"bulk_attendance_record": name}):
            continue
        write_bulk_rows(frappe.get_doc("Bulk Attendance Record", name))

    # existing overtime records came from Bulk Attendance
    frappe.db.set_value(
        "Project Overtime", {"bulk_attendance_record": ["is", "set"]}, "source", "Bulk Attendance", update_modified=False
    )

    # periods already costed: stamp the ledger with the slip
    slips = frappe.get_all(
        "Project Salary Expense", fields=["salary_slip", "employee", "from_date", "to_date"], distinct=True
    )
    for slip in slips:
        if not (slip.salary_slip and slip.from_date and slip.to_date):
            continue
        frappe.db.set_value(
            PAL,
            {
                "employee": slip.employee,
                "attendance_date": ["between", [slip.from_date, slip.to_date]],
                "salary_slip": ["is", "not set"],
            },
            "salary_slip",
            slip.salary_slip,
            update_modified=False,
        )
