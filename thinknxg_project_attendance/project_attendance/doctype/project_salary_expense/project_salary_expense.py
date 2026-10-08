import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProjectSalaryExpense(Document):
    def validate(self):
        self.total_amount = flt(self.salary_amount) + flt(self.overtime_amount) + flt(self.other_earnings)

    def on_trash(self):
        if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
            frappe.throw(
                _("Journal Entry {0} is posted for this Project Salary Expense. Cancel it first.").format(
                    self.journal_entry
                )
            )
