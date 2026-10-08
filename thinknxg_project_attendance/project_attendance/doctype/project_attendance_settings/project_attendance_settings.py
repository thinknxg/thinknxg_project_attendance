import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from thinknxg_project_attendance.utils.common import METHOD_FIXED


class ProjectAttendanceSettings(Document):
    def validate(self):
        if flt(self.normal_working_hours) <= 0 or flt(self.normal_working_hours) > 24:
            frappe.throw(_("Normal Working Hours / Day must be between 0 and 24."))
        if cint(self.monthly_divisor_days) < 0 or cint(self.monthly_divisor_days) > 31:
            frappe.throw(_("Monthly Divisor Days must be between 0 and 31."))
        if self.overtime_calculation_method == METHOD_FIXED and flt(self.fixed_overtime_rate) <= 0:
            frappe.throw(_("Set the Fixed OT Rate."))

        for fieldname in ("overtime_salary_component", "basic_salary_component"):
            component = self.get(fieldname)
            if component and frappe.db.get_value("Salary Component", component, "type") != "Earning":
                frappe.throw(_("Salary Component {0} must be of type Earning.").format(component))

        if self.basic_salary_component and self.basic_salary_component == self.overtime_salary_component:
            frappe.throw(_("Basic Salary Component and Overtime Component cannot be the same."))

        if self.fallback_expense_account:
            root_type, is_group = frappe.db.get_value(
                "Account", self.fallback_expense_account, ["root_type", "is_group"]
            )
            if is_group or root_type != "Expense":
                frappe.throw(_("Fallback Salary Expense Account must be a non-group Expense account."))
