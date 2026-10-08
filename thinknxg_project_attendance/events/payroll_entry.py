import frappe
from frappe import _
from frappe.utils import cint

from thinknxg_project_attendance.utils.approval import count_pending
from thinknxg_project_attendance.utils.common import get_settings
from thinknxg_project_attendance.utils.overtime import post_overtime_for_employees


def before_submit(doc, method=None):
    """Post the approved checkin overtime as Additional Salary before the salary slips are created."""
    employees = [row.employee for row in doc.get("employees") or [] if row.employee]
    if not employees:
        return

    settings = get_settings()
    pending = count_pending(employees, doc.end_date) if cint(settings.require_overtime_approval) else 0
    link = '<a href="/desk/project-overtime?approval_status=Pending">{0}</a>'.format(_("Project Overtime"))
    if pending and cint(settings.block_payroll_on_pending_overtime):
        frappe.throw(
            _("{0} overtime record(s) of these employees are still pending approval. Approve or reject them in {1} first.").format(
                pending, link
            ),
            title=_("Overtime Pending Approval"),
        )

    # everything approved up to the period end, including overtime approved after an earlier payroll
    posted, failed = post_overtime_for_employees(employees, None, doc.end_date, doc.end_date)

    if pending:
        frappe.msgprint(
            _("{0} overtime record(s) are still pending approval in {1} and are not paid in this payroll. Overtime approved later is paid with the next payroll.").format(
                pending, link
            ),
            title=_("Overtime Pending Approval"),
            indicator="orange",
        )
    if failed:
        frappe.msgprint(
            _("Checkin overtime could not be posted to payroll for:")
            + "<ul>"
            + "".join(f"<li>{employee}: {frappe.utils.strip_html(message)}</li>" for employee, message in failed[:20])
            + "</ul>"
            + _("Fix the cause and use Post Unpaid Overtime in the Project Overtime list before creating the slips."),
            title=_("Overtime Not Posted"),
            indicator="orange",
        )
