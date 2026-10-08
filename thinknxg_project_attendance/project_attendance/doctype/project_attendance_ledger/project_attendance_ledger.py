import frappe
from frappe import _
from frappe.model.document import Document


class ProjectAttendanceLedger(Document):
    def on_trash(self):
        if self.salary_slip:
            frappe.throw(
                _("This ledger row is costed in Salary Slip {0} and cannot be deleted.").format(self.salary_slip)
            )
