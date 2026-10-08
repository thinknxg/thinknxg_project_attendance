import frappe
from frappe import _

from thinknxg_project_attendance.project_attendance.report.project_salary_expense_report.project_salary_expense_report import (
    build_query,
    get_chart,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = build_query(filters, group_by_employee=False).run(as_dict=True)
    currency = None
    if filters.get("company"):
        currency = frappe.get_cached_value("Company", filters.company, "default_currency")
    for row in data:
        row.currency = currency
        if not row.project:
            row.project_name = _("Unallocated")
    return get_columns(), data, None, get_chart(data)


def get_columns():
    return [
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 170},
        {"label": _("Project Name"), "fieldname": "project_name", "fieldtype": "Data", "width": 220},
        {"label": _("Employees"), "fieldname": "employees", "fieldtype": "Int", "width": 100},
        {"label": _("Days Worked"), "fieldname": "days_worked", "fieldtype": "Float", "precision": 2, "width": 120},
        {"label": _("Regular Hours"), "fieldname": "regular_hours", "fieldtype": "Float", "width": 120},
        {"label": _("Salary"), "fieldname": "salary_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": _("Other Earnings"), "fieldname": "other_earnings", "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": _("Overtime Hours"), "fieldname": "overtime_hours", "fieldtype": "Float", "width": 130},
        {"label": _("Overtime Amount"), "fieldname": "overtime_amount", "fieldtype": "Currency", "options": "currency", "width": 150},
        {"label": _("Total Labour Cost"), "fieldname": "total_amount", "fieldtype": "Currency", "options": "currency", "width": 160},
        {"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
