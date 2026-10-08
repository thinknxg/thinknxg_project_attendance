import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from thinknxg_project_attendance.utils.common import currency_precision


class ProjectOvertime(Document):
    def validate(self):
        if flt(self.overtime_hours) <= 0:
            frappe.throw(_("OT Hours must be greater than zero."))
        # payable hours: the approved hours once approved, nothing when rejected,
        # the recorded hours as an estimate while pending
        if self.approval_status == "Approved":
            self.approved_hours = flt(self.approved_hours) or flt(self.overtime_hours)
            if flt(self.approved_hours) > flt(self.overtime_hours) + 0.0001:
                frappe.throw(_("Approved OT Hours cannot exceed the recorded OT Hours."))
            payable = flt(self.approved_hours)
        elif self.approval_status == "Rejected":
            self.approved_hours = 0
            payable = 0.0
        else:
            self.approval_status = "Pending"
            self.approved_hours = 0
            payable = flt(self.overtime_hours)
        self.overtime_amount = flt(payable * flt(self.overtime_rate), currency_precision())
        if self.docstatus == 0:
            self.status = "Unpaid"

    def before_cancel(self):
        if self.salary_slip:
            frappe.throw(
                _("Overtime {0} is already paid in Salary Slip {1}.").format(self.name, self.salary_slip)
            )

    def on_cancel(self):
        self.db_set("status", "Cancelled")
