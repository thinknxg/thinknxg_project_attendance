import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from thinknxg_project_attendance.utils.common import currency_precision


class ProjectOvertime(Document):
    def validate(self):
        if flt(self.overtime_hours) <= 0:
            frappe.throw(_("OT Hours must be greater than zero."))
        self.overtime_amount = flt(flt(self.overtime_hours) * flt(self.overtime_rate), currency_precision())
        if self.docstatus == 0:
            self.status = "Unpaid"

    def before_cancel(self):
        if self.salary_slip:
            frappe.throw(
                _("Overtime {0} is already paid in Salary Slip {1}.").format(self.name, self.salary_slip)
            )

    def on_cancel(self):
        self.db_set("status", "Cancelled")
