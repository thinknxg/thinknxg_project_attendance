import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SETTINGS = "Project Attendance Settings"

CUSTOM_FIELDS = {
    "Attendance": [
        {
            "fieldname": "nxg_project_section",
            "fieldtype": "Section Break",
            "label": "Project Attendance",
            "insert_after": "shift",
            "collapsible": 1,
        },
        {
            "fieldname": "nxg_project",
            "fieldtype": "Link",
            "label": "Project",
            "options": "Project",
            "insert_after": "nxg_project_section",
            "in_standard_filter": 1,
            "search_index": 1,
        },
        {
            "fieldname": "nxg_overtime_hours",
            "fieldtype": "Float",
            "label": "Project Overtime Hours",
            "insert_after": "nxg_project",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "nxg_column_break",
            "fieldtype": "Column Break",
            "insert_after": "nxg_overtime_hours",
        },
        {
            "fieldname": "nxg_bulk_attendance_record",
            "fieldtype": "Link",
            "label": "Bulk Attendance Record",
            "options": "Bulk Attendance Record",
            "insert_after": "nxg_column_break",
            "read_only": 1,
            "no_copy": 1,
            "search_index": 1,
        },
    ],
    "Employee": [
        {
            "fieldname": "nxg_overtime_hourly_rate",
            "fieldtype": "Currency",
            "label": "Overtime Hourly Rate",
            "insert_after": "grade",
            "description": "Used by thinkNXG Project Attendance when the overtime method is 'Hourly Rate x OT Hours'.",
        },
    ],
    "Employee Grade": [
        {
            "fieldname": "nxg_overtime_hourly_rate",
            "fieldtype": "Currency",
            "label": "Overtime Hourly Rate",
            "insert_after": "default_salary_structure",
            "description": "Fallback overtime hourly rate for employees of this grade.",
        },
    ],
    "Journal Entry": [
        {
            "fieldname": "nxg_project_salary_reclass",
            "fieldtype": "Check",
            "label": "Project Salary Re-classification",
            "insert_after": "user_remark",
            "read_only": 1,
            "no_copy": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "nxg_payroll_entry",
            "fieldtype": "Link",
            "label": "Payroll Entry (Project Salary)",
            "options": "Payroll Entry",
            "insert_after": "nxg_project_salary_reclass",
            "read_only": 1,
            "no_copy": 1,
            "print_hide": 1,
            "depends_on": "nxg_project_salary_reclass",
        },
    ],
}

DEFAULTS = {
    "overtime_calculation_method": "Basic / Working Hours x Multiplier",
    "normal_working_hours": 8,
    "monthly_divisor_days": 30,
    "overtime_multiplier": 1.25,
    "holiday_overtime_multiplier": 1.5,
    "max_overtime_hours_per_day": 4,
    "create_additional_salary": 1,
    "salary_allocation_method": "Working Days",
    "post_reclass_journal": 1,
    "auto_submit_journal": 1,
}


def after_install():
    make_custom_fields()
    set_default_settings()


def after_migrate():
    make_custom_fields()
    set_default_settings()


def make_custom_fields():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True, update=True)


def set_default_settings():
    """Fill the settings once; never overwrite values a user has already saved."""
    if frappe.db.exists("Singles", {"doctype": SETTINGS, "field": "overtime_calculation_method"}):
        return

    settings = frappe.get_single(SETTINGS)
    for key, value in DEFAULTS.items():
        settings.set(key, value)
    settings.overtime_salary_component = get_or_create_overtime_component()
    settings.flags.ignore_mandatory = True
    settings.flags.ignore_permissions = True
    settings.save()


def get_or_create_overtime_component():
    try:
        if frappe.db.exists("Salary Component", "Overtime"):
            if frappe.db.get_value("Salary Component", "Overtime", "type") == "Earning":
                return "Overtime"
            return None

        abbr = "OT"
        if frappe.db.exists("Salary Component", {"salary_component_abbr": abbr}):
            abbr = "NXGOT"

        component = frappe.get_doc(
            {
                "doctype": "Salary Component",
                "salary_component": "Overtime",
                "salary_component_abbr": abbr,
                "type": "Earning",
                "depends_on_payment_days": 0,
                "description": "Project overtime posted by thinkNXG Project Attendance",
            }
        )
        component.flags.ignore_permissions = True
        component.insert()
        return component.name
    except Exception:
        frappe.log_error(title="thinkNXG Project Attendance: could not create Overtime component")
        return None


def before_uninstall():
    for doctype, fields in CUSTOM_FIELDS.items():
        for field in fields:
            name = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]})
            if name:
                frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
