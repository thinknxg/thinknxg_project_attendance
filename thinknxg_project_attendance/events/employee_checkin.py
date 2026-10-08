import frappe
from frappe import _


def validate(doc, method=None):
    """Stamp the project of the device / site when the checkin itself carries none."""
    if doc.get("nxg_project"):
        if doc.get("nxg_project_source") != "Device Mapping" or doc.has_value_changed("nxg_project"):
            doc.nxg_project_source = "Checkin"
        return

    doc.nxg_project_source = None
    if doc.get("device_id"):
        project = frappe.db.get_value(
            "Project Device Mapping", {"device_id": doc.device_id, "disabled": 0}, "project"
        )
        if project:
            doc.nxg_project = project
            doc.nxg_project_source = "Device Mapping"


def on_update(doc, method=None):
    """A project corrected on a checkin that is already linked to Attendance rebuilds that day."""
    if doc.is_new() or not doc.get("attendance"):
        return
    if not (doc.has_value_changed("nxg_project") or doc.has_value_changed("nxg_is_project_override")):
        return

    from thinknxg_project_attendance.utils.ledger import safe_process

    result = safe_process(doc.attendance)
    if result == "costed":
        frappe.msgprint(
            _("This day is already costed in a Salary Slip. The Project Attendance Ledger was not changed."),
            indicator="orange",
            alert=True,
        )
    elif result == "processed":
        frappe.msgprint(_("Project Attendance Ledger updated."), indicator="green", alert=True)
