import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class EmployeeProjectAssignment(Document):
    def validate(self):
        if self.to_date and getdate(self.from_date) > getdate(self.to_date):
            frappe.throw(_("From Date cannot be after To Date."))

        if flt(self.allocation_percent) < 0 or flt(self.allocation_percent) > 100:
            frappe.throw(_("Allocation % must be between 0 and 100."))

        project = frappe.db.get_value("Project", self.project, ["status", "is_active", "company"], as_dict=True)
        if project and (project.status == "Cancelled" or project.is_active == "No"):
            frappe.throw(_("Project {0} is cancelled or inactive.").format(frappe.bold(self.project)))

        self.company = frappe.db.get_value("Employee", self.employee, "company")
        if project and project.company and self.company and project.company != self.company:
            frappe.throw(
                _("Project {0} belongs to company {1}.").format(frappe.bold(self.project), project.company)
            )

        if not self.disabled:
            self.validate_overlap()

    def validate_overlap(self):
        """Overlapping assignments share the hours by percentage, so together they may not exceed 100."""
        others = frappe.get_all(
            "Employee Project Assignment",
            filters={"employee": self.employee, "disabled": 0, "name": ["!=", self.name or "new"]},
            fields=["name", "project", "from_date", "to_date", "allocation_percent"],
        )
        start = getdate(self.from_date)
        end = getdate(self.to_date) if self.to_date else None
        overlapping = []
        for other in others:
            other_start = getdate(other.from_date)
            other_end = getdate(other.to_date) if other.to_date else None
            if (end is None or other_start <= end) and (other_end is None or other_end >= start):
                overlapping.append(other)

        if not overlapping:
            return

        total = flt(self.allocation_percent) + sum(flt(o.allocation_percent) for o in overlapping)
        if total > 100.0001:
            frappe.throw(
                _(
                    "Overlapping assignments of employee {0} ({1}) add up to {2}%. "
                    "Reduce the Allocation %, or end the earlier assignment with a To Date."
                ).format(self.employee, ", ".join(o.name for o in overlapping), flt(total, 2)),
                title=_("Allocation Above 100%"),
            )
