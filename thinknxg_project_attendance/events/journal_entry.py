import frappe

from thinknxg_project_attendance.utils.allocation import PSE


def on_submit(doc, method=None):
    """When the payroll accrual journal is submitted, post the project re-classification."""
    if doc.get("nxg_project_salary_reclass"):
        return

    payroll_entries = {
        row.reference_name
        for row in doc.get("accounts") or []
        if row.get("reference_type") == "Payroll Entry" and row.get("reference_name")
    }
    for payroll_entry in payroll_entries:
        if not frappe.db.exists(PSE, {"payroll_entry": payroll_entry, "gl_status": "Not Posted"}):
            continue
        frappe.enqueue(
            "thinknxg_project_attendance.utils.journal.post_in_background",
            queue="short",
            enqueue_after_commit=True,
            payroll_entry=payroll_entry,
        )


def on_cancel(doc, method=None):
    if doc.get("nxg_project_salary_reclass"):
        from thinknxg_project_attendance.utils.journal import reset_expenses_for_journal

        reset_expenses_for_journal(doc.name)
