"""Project Attendance Hours: hours and days per project straight from the Project Attendance Ledger.

Available as soon as attendance is processed - it does not wait for payroll.
"""
import frappe
from frappe import _
from frappe.query_builder.functions import Sum


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(filters), get_data(filters)


def get_columns(filters):
    columns = [
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
        {"label": _("Project Name"), "fieldname": "project_name", "fieldtype": "Data", "width": 180},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
    ]
    if filters.get("group_by") == "Day":
        columns.append({"label": _("Date"), "fieldname": "attendance_date", "fieldtype": "Date", "width": 110})
    columns += [
        {"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 140},
        {"label": _("Days"), "fieldname": "days", "fieldtype": "Float", "precision": 2, "width": 90},
        {"label": _("Regular Hours"), "fieldname": "regular_hours", "fieldtype": "Float", "width": 120},
        {"label": _("Overtime Hours"), "fieldname": "overtime_hours", "fieldtype": "Float", "width": 130},
        {"label": _("Total Hours"), "fieldname": "working_hours", "fieldtype": "Float", "width": 110},
    ]
    return columns


def get_data(filters):
    ledger = frappe.qb.DocType("Project Attendance Ledger")
    project = frappe.qb.DocType("Project")

    query = (
        frappe.qb.from_(ledger)
        .left_join(project)
        .on(project.name == ledger.project)
        .select(
            ledger.project,
            project.project_name,
            ledger.employee,
            ledger.employee_name,
            ledger.source,
            Sum(ledger.day_fraction).as_("days"),
            Sum(ledger.regular_hours).as_("regular_hours"),
            Sum(ledger.overtime_hours).as_("overtime_hours"),
            Sum(ledger.working_hours).as_("working_hours"),
        )
        .groupby(ledger.project, project.project_name, ledger.employee, ledger.employee_name, ledger.source)
        .orderby(ledger.project)
        .orderby(ledger.employee)
    )
    if filters.get("group_by") == "Day":
        query = query.select(ledger.attendance_date).groupby(ledger.attendance_date).orderby(ledger.attendance_date)

    if filters.get("company"):
        query = query.where(ledger.company == filters.company)
    if filters.get("from_date"):
        query = query.where(ledger.attendance_date >= filters.from_date)
    if filters.get("to_date"):
        query = query.where(ledger.attendance_date <= filters.to_date)
    for field in ("project", "employee", "department", "source"):
        if filters.get(field):
            query = query.where(ledger[field] == filters.get(field))
    if filters.get("unallocated_only"):
        query = query.where(ledger.is_unallocated == 1)
    if filters.get("uncosted_only"):
        query = query.where(ledger.salary_slip.isnull() | (ledger.salary_slip == ""))

    data = query.run(as_dict=True)
    for row in data:
        if not row.project:
            row.project_name = _("Unallocated")
    return data
