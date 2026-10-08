"""Overtime approval: checkin overtime is paid only after someone approves it."""
import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from thinknxg_project_attendance.utils.common import currency_precision, get_settings

POT = "Project Overtime"
ACTIONS = {"Approve": "Approved", "Reject": "Rejected", "Reset": "Pending"}


def can_approve_overtime(user=None):
    roles = set(frappe.get_roles(user or frappe.session.user))
    allowed = {"HR Manager", "System Manager"}
    extra = get_settings().overtime_approver_role
    if extra:
        allowed.add(extra)
    return bool(roles & allowed)


@frappe.whitelist()
def get_approval_context():
    """For the client: may this user approve, and is approval switched on."""
    settings = get_settings()
    return {
        "can_approve": can_approve_overtime(),
        "required": cint(settings.require_overtime_approval),
    }


def initial_approval(settings=None):
    """Approval values of a newly calculated checkin overtime record."""
    settings = settings or get_settings()
    if cint(settings.require_overtime_approval):
        return {"approval_status": "Pending", "approved_hours": 0}
    return {"approval_status": "Approved", "approval_remarks": "Approval not required"}


@frappe.whitelist()
def set_overtime_approval(names, action, approved_hours=None, remarks=None):
    """Approve, reject or reset one or many Project Overtime records.

    approved_hours (optional, Approve only) pays fewer hours than recorded; with several records
    it is used as an upper limit per record.
    """
    from thinknxg_project_attendance.utils.overtime import release_additional_salary

    if action not in ACTIONS:
        frappe.throw(_("Invalid action: {0}").format(action))
    if not can_approve_overtime():
        frappe.throw(_("You are not allowed to approve overtime."), frappe.PermissionError)

    if isinstance(names, str):
        names = frappe.parse_json(names) if names.strip().startswith("[") else [names]
    limit = flt(approved_hours) if approved_hours not in (None, "") else None
    if limit is not None and limit <= 0 and action == "Approve":
        frappe.throw(_("Approved OT Hours must be greater than zero. Use Reject instead."))

    precision = currency_precision()
    status = ACTIONS[action]
    changed, skipped = 0, []

    for name in names:
        record = frappe.db.get_value(
            POT,
            name,
            [
                "name",
                "docstatus",
                "salary_slip",
                "additional_salary",
                "bulk_attendance_record",
                "overtime_hours",
                "overtime_rate",
                "approval_status",
                "approved_hours",
            ],
            as_dict=True,
        )
        if not record or record.docstatus != 1:
            skipped.append((name, _("not a submitted record")))
            continue
        if record.salary_slip:
            skipped.append((name, _("already paid in Salary Slip {0}").format(record.salary_slip)))
            continue
        if record.bulk_attendance_record:
            skipped.append(
                (name, _("from Bulk Attendance Record {0}: cancel and amend that record instead").format(record.bulk_attendance_record))
            )
            continue

        if action == "Approve":
            hours = flt(record.overtime_hours)
            if limit is not None:
                if len(names) == 1 and limit > hours + 0.0001:
                    frappe.throw(
                        _("Approved OT Hours ({0}) cannot exceed the recorded OT Hours ({1}).").format(limit, hours)
                    )
                hours = min(hours, limit)
        else:
            hours = 0.0

        if record.approval_status == status and abs(flt(record.approved_hours) - hours) < 0.0001:
            continue  # nothing to change

        if record.additional_salary:
            # already posted to payroll but not yet in a slip: take the posting back first.
            # The other records of that Additional Salary stay approved and are posted again.
            try:
                release_additional_salary(record.additional_salary)
            except frappe.ValidationError as exc:
                skipped.append((name, frappe.utils.strip_html(str(exc))))
                continue

        payable = hours if action == "Approve" else (0.0 if action == "Reject" else flt(record.overtime_hours))
        frappe.db.set_value(
            POT,
            name,
            {
                "approval_status": status,
                "approved_hours": hours,
                "overtime_amount": flt(payable * flt(record.overtime_rate), precision),
                "approved_by": None if action == "Reset" else frappe.session.user,
                "approved_on": None if action == "Reset" else now_datetime(),
                "approval_remarks": remarks,
            },
        )
        text = {
            "Approve": _("Overtime approved: {0} of {1} hours").format(hours, flt(record.overtime_hours)),
            "Reject": _("Overtime rejected"),
            "Reset": _("Overtime approval reset to Pending"),
        }[action]
        if remarks:
            text += f" - {frappe.utils.escape_html(remarks)}"
        frappe.get_doc(POT, name).add_comment("Info", text)
        changed += 1

    if skipped:
        frappe.msgprint(
            _("Not changed:")
            + "<ul>"
            + "".join(f"<li>{name}: {reason}</li>" for name, reason in skipped[:25])
            + "</ul>",
            title=_("Some Records Were Skipped"),
            indicator="orange",
        )
    return {"changed": changed, "skipped": len(skipped)}


def count_pending(employees, to_date):
    """Pending overtime records of employees up to a date (for the payroll warning)."""
    if not employees:
        return 0
    return frappe.db.count(
        POT,
        {
            "employee": ["in", list(employees)],
            "docstatus": 1,
            "approval_status": "Pending",
            "attendance_date": ["<=", to_date],
        },
    )
