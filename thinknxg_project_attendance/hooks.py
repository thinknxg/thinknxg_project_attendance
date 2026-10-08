app_name = "thinknxg_project_attendance"
app_title = "thinkNXG Project Attendance"
app_publisher = "thinkNXG"
app_description = "Project based bulk employee attendance, overtime and project salary costing"
app_email = "admin@example.com"
app_license = "mit"
app_logo_url = "/assets/thinknxg_project_attendance/images/logo.svg"
app_home = "/desk/project-attendance"

required_apps = ["frappe/erpnext", "frappe/hrms"]

add_to_apps_screen = [
    {
        "name": "thinknxg_project_attendance",
        "logo": "/assets/thinknxg_project_attendance/images/logo.svg",
        "title": "Project Attendance",
        "route": app_home,
    }
]

# Installation
after_install = "thinknxg_project_attendance.install.after_install"
after_migrate = "thinknxg_project_attendance.install.after_migrate"
before_uninstall = "thinknxg_project_attendance.install.before_uninstall"

# Client scripts on standard doctypes (no core files are modified)
doctype_js = {
    "Payroll Entry": "public/js/payroll_entry.js",
}

# Document events on standard doctypes
doc_events = {
    "Salary Slip": {
        "on_submit": "thinknxg_project_attendance.events.salary_slip.on_submit",
        "on_cancel": "thinknxg_project_attendance.events.salary_slip.on_cancel",
    },
    "Attendance": {
        "on_submit": "thinknxg_project_attendance.events.attendance.on_submit",
        "on_cancel": "thinknxg_project_attendance.events.attendance.on_cancel",
    },
    "Employee Checkin": {
        "validate": "thinknxg_project_attendance.events.employee_checkin.validate",
        "on_update": "thinknxg_project_attendance.events.employee_checkin.on_update",
    },
    "Payroll Entry": {
        "before_submit": "thinknxg_project_attendance.events.payroll_entry.before_submit",
    },
    "Journal Entry": {
        "on_submit": "thinknxg_project_attendance.events.journal_entry.on_submit",
        "on_cancel": "thinknxg_project_attendance.events.journal_entry.on_cancel",
    },
}

scheduler_events = {
    "daily": [
        "thinknxg_project_attendance.utils.journal.post_pending_project_journals",
        "thinknxg_project_attendance.utils.ledger.reconcile_ledger",
    ],
}
