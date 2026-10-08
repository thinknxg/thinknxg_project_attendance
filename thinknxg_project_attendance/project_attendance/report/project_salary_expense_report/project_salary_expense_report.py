import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    return columns, data, None, chart


def get_columns():
    return [
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
        {"label": _("Project Name"), "fieldname": "project_name", "fieldtype": "Data", "width": 180},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
        {"label": _("Grade"), "fieldname": "grade", "fieldtype": "Link", "options": "Employee Grade", "width": 100},
        {"label": _("Days Worked"), "fieldname": "days_worked", "fieldtype": "Float", "precision": 2, "width": 110},
        {"label": _("Regular Hours"), "fieldname": "regular_hours", "fieldtype": "Float", "width": 120},
        {"label": _("Basic Salary"), "fieldname": "salary_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
        {"label": _("Overtime Hours"), "fieldname": "overtime_hours", "fieldtype": "Float", "width": 120},
        {"label": _("Overtime Amount"), "fieldname": "overtime_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": _("Other Salary"), "fieldname": "other_earnings", "fieldtype": "Currency", "options": "currency", "width": 130},
        {"label": _("Total Salary Expense"), "fieldname": "total_amount", "fieldtype": "Currency", "options": "currency", "width": 160},
        {"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def build_query(filters, group_by_employee=True):
    pse = frappe.qb.DocType("Project Salary Expense")
    project = frappe.qb.DocType("Project")

    query = (
        frappe.qb.from_(pse)
        .left_join(project)
        .on(project.name == pse.project)
        .select(
            pse.project,
            project.project_name,
            Sum(pse.days_worked).as_("days_worked"),
            Sum(pse.working_hours).as_("regular_hours"),
            Sum(pse.salary_amount).as_("salary_amount"),
            Sum(pse.overtime_hours).as_("overtime_hours"),
            Sum(pse.overtime_amount).as_("overtime_amount"),
            Sum(pse.other_earnings).as_("other_earnings"),
            Sum(pse.total_amount).as_("total_amount"),
        )
        .where(pse.docstatus < 2)
        .groupby(pse.project, project.project_name)
        .orderby(pse.project)
    )

    if group_by_employee:
        query = (
            query.select(pse.employee, pse.employee_name, pse.department, pse.grade)
            .groupby(pse.employee, pse.employee_name, pse.department, pse.grade)
            .orderby(pse.employee)
        )
    else:
        query = query.select(Count(pse.employee).distinct().as_("employees"))

    if filters.get("company"):
        query = query.where(pse.company == filters.company)
    if filters.get("from_date"):
        query = query.where(pse.posting_date >= filters.from_date)
    if filters.get("to_date"):
        query = query.where(pse.posting_date <= filters.to_date)
    for field in ("project", "employee", "department", "grade", "payroll_entry"):
        if filters.get(field):
            query = query.where(pse[field] == filters.get(field))
    if filters.get("source"):
        query = query.where(pse.attendance_sources.like(f"%{filters.source}%"))
    if filters.get("cost_center"):
        query = query.where(
            (pse.cost_center == filters.cost_center) | (pse.source_cost_center == filters.cost_center)
        )
    return query


def get_data(filters):
    data = build_query(filters).run(as_dict=True)
    currency = None
    if filters.get("company"):
        currency = frappe.get_cached_value("Company", filters.company, "default_currency")
    for row in data:
        row.currency = currency
        if not row.project:
            row.project_name = _("Unallocated")
    return data


def get_chart(data):
    if not data:
        return None
    totals = {}
    for row in data:
        bucket = totals.setdefault(row.project or _("Unallocated"), {"salary": 0.0, "overtime": 0.0})
        bucket["salary"] += (row.salary_amount or 0) + (row.other_earnings or 0)
        bucket["overtime"] += row.overtime_amount or 0
    labels = list(totals)[:20]
    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": _("Salary"), "values": [totals[p]["salary"] for p in labels]},
                {"name": _("Overtime"), "values": [totals[p]["overtime"] for p in labels]},
            ],
        },
        "type": "bar",
        "barOptions": {"stacked": 1},
        "fieldtype": "Currency",
    }
