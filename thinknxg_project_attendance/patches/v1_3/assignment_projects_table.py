"""v1.3: Employee Project Assignment holds several projects in a table.

Move the single project / allocation % of each existing assignment into the table. Assignments
of one employee that overlapped (the old way to split between projects) are left as they are:
costing still combines them, and the form asks to merge them the next time one is edited.
"""
import frappe
from frappe.utils import flt


def execute():
    if not frappe.db.has_column("Employee Project Assignment", "project"):
        return

    rows = frappe.db.sql(
        """select name, project, allocation_percent, is_primary
        from `tabEmployee Project Assignment`
        where ifnull(project, '') != ''""",
        as_dict=True,
    )
    for row in rows:
        if frappe.db.exists(
            "Employee Project Allocation", {"parent": row.name, "parenttype": "Employee Project Assignment"}
        ):
            continue
        percent = flt(row.allocation_percent) or 100
        frappe.get_doc(
            {
                "doctype": "Employee Project Allocation",
                "parent": row.name,
                "parenttype": "Employee Project Assignment",
                "parentfield": "projects",
                "idx": 1,
                "project": row.project,
                "allocation_percent": percent,
                "is_primary": 1,
            }
        ).db_insert()
        frappe.db.set_value(
            "Employee Project Assignment",
            row.name,
            {"total_allocation": percent, "project_summary": f"{row.project} {percent:g}%"},
            update_modified=False,
        )
