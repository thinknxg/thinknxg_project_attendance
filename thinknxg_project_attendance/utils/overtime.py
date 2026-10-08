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
