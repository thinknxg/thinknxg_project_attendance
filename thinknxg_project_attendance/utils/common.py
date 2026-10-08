import calendar

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

SETTINGS = "Project Attendance Settings"
WORKED_STATUSES = ("Present", "Half Day", "Work From Home")
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

METHOD_BASIC = "Basic / Working Hours x Multiplier"
METHOD_HOURLY = "Hourly Rate x OT Hours"
METHOD_FIXED = "Fixed OT Rate"


def get_settings():
    return frappe.get_cached_doc(SETTINGS)


def currency_precision():
    try:
        from erpnext.accounts.utils import get_currency_precision

        return cint(get_currency_precision()) or 2
    except Exception:
        return cint(frappe.db.get_default("currency_precision")) or 2


def get_month_range(month_name, year):
    """Return (first_day, last_day) of the given month name / year."""
    if month_name not in MONTHS:
        frappe.throw(_("Invalid Posting Month: {0}").format(month_name))
    year = cint(year)
    if year < 2000 or year > 2100:
        frappe.throw(_("Invalid Year: {0}").format(year))
    month = MONTHS.index(month_name) + 1
    last = calendar.monthrange(year, month)[1]
    return getdate(f"{year}-{month:02d}-01"), getdate(f"{year}-{month:02d}-{last:02d}")


def daterange(start, end):
    day = getdate(start)
    end = getdate(end)
    while day <= end:
        yield day
        day = add_days(day, 1)


def get_holiday_dates(employee, company, start, end):
    """Holiday dates (including weekly offs) of the employee between two dates."""
    try:
        from hrms.utils.holiday_list import get_holiday_dates_between_range

        dates = get_holiday_dates_between_range(
            employee, start, end, raise_exception_for_holiday_list=False
        )
        return {getdate(d) for d in dates or []}
    except Exception:
        pass

    # Fallback for installations without holiday list assignments
    holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
    if not holiday_list and company:
        holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
    if not holiday_list:
        return set()
    dates = frappe.get_all(
        "Holiday",
        filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
        pluck="holiday_date",
    )
    return {getdate(d) for d in dates}


def get_approved_leaves(employee, start, end):
    """Map of date -> {leave_type, name, half_day} for approved leave applications."""
    leaves = {}
    applications = frappe.get_all(
        "Leave Application",
        filters={
            "employee": employee,
            "docstatus": 1,
            "status": "Approved",
            "from_date": ["<=", end],
            "to_date": [">=", start],
        },
        fields=["name", "leave_type", "from_date", "to_date", "half_day", "half_day_date"],
    )
    start, end = getdate(start), getdate(end)
    for app in applications:
        half_day_date = getdate(app.half_day_date) if app.half_day_date else None
        if cint(app.half_day) and not half_day_date and getdate(app.from_date) == getdate(app.to_date):
            half_day_date = getdate(app.from_date)
        for day in daterange(max(getdate(app.from_date), start), min(getdate(app.to_date), end)):
            leaves[day] = frappe._dict(
                name=app.name,
                leave_type=app.leave_type,
                half_day=1 if (half_day_date and day == half_day_date) else 0,
            )
    return leaves


def get_salary_assignment(employee, on_date):
    """Latest submitted Salary Structure Assignment applicable on the date."""
    rows = frappe.get_all(
        "Salary Structure Assignment",
        filters={"employee": employee, "docstatus": 1, "from_date": ["<=", on_date]},
        fields=["name", "base", "currency", "salary_structure", "from_date"],
        order_by="from_date desc",
        limit=1,
    )
    return rows[0] if rows else None


def get_payroll_cost_center(employee, company, payroll_entry=None):
    """Mirror of the default cost center resolution used by the Payroll Entry."""
    cost_center, department = frappe.get_cached_value(
        "Employee", employee, ["payroll_cost_center", "department"]
    )
    if not cost_center and department:
        cost_center = frappe.get_cached_value("Department", department, "payroll_cost_center")
    if not cost_center and payroll_entry:
        cost_center = frappe.db.get_value("Payroll Entry", payroll_entry, "cost_center")
    if not cost_center:
        cost_center = frappe.get_cached_value("Company", company, "cost_center")
    return cost_center


def distribute(amount, weights, precision=2):
    """Split an amount over weighted keys; the rounding difference goes to the last key."""
    keys = [k for k, w in weights.items() if flt(w) > 0]
    total = sum(flt(weights[k]) for k in keys)
    result = {}
    if not keys or not total:
        return result
    running = 0.0
    for key in keys[:-1]:
        value = flt(flt(amount) * flt(weights[key]) / total, precision)
        result[key] = value
        running += value
    result[keys[-1]] = flt(flt(amount) - running, precision)
    return result
