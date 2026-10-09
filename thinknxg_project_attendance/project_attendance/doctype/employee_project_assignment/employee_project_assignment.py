import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_link_to_form, getdate


class EmployeeProjectAssignment(Document):
    def validate(self):
        if self.to_date and getdate(self.from_date) > getdate(self.to_date):
            frappe.throw(_("From Date cannot be after To Date."))

        self.company = frappe.db.get_value("Employee", self.employee, "company")
        self.validate_projects()
        if not cint(self.disabled):
            self.validate_overlap()

    def validate_projects(self):
        if not self.projects:
            frappe.throw(_("Add at least one project."))

        # a single project is always 100%
        if len(self.projects) == 1 and not flt(self.projects[0].allocation_percent):
            self.projects[0].allocation_percent = 100

        seen = set()
        primaries = 0
        total = 0.0
        for row in self.projects:
            if row.project in seen:
                frappe.throw(_("Row {0}: project {1} is entered more than once.").format(row.idx, row.project))
            seen.add(row.project)

            percent = flt(row.allocation_percent)
            if percent <= 0 or percent > 100:
                frappe.throw(_("Row {0}: Allocation % must be greater than 0 and at most 100.").format(row.idx))
            total += percent
            primaries += cint(row.is_primary)

            project = frappe.db.get_value(
                "Project", row.project, ["status", "is_active", "company"], as_dict=True
            )
            if project and (project.status == "Cancelled" or project.is_active == "No"):
                frappe.throw(
                    _("Row {0}: project {1} is cancelled or inactive.").format(row.idx, frappe.bold(row.project))
                )
            if project and project.company and self.company and project.company != self.company:
                frappe.throw(
                    _("Row {0}: project {1} belongs to company {2}.").format(
                        row.idx, frappe.bold(row.project), project.company
                    )
                )

        if abs(total - 100) > 0.01:
            frappe.throw(
                _("The Allocation % of all projects must add up to 100. Current total: {0}.").format(flt(total, 2)),
                title=_("Allocation Not 100%"),
            )
        if primaries > 1:
            frappe.throw(_("Only one project can be marked Is Primary."))
        if primaries == 0:
            # the largest share is the primary project
            max(self.projects, key=lambda r: flt(r.allocation_percent)).is_primary = 1

        self.total_allocation = flt(total, 2)
        self.project_summary = ", ".join(
            f"{row.project} {flt(row.allocation_percent):g}%" for row in self.projects
        )[:500]

    def validate_overlap(self):
        """One active assignment per employee and date: the project split lives inside the assignment."""
        others = frappe.get_all(
            "Employee Project Assignment",
            filters={"employee": self.employee, "disabled": 0, "name": ["!=", self.name or "new"]},
            fields=["name", "from_date", "to_date"],
        )
        start = getdate(self.from_date)
        end = getdate(self.to_date) if self.to_date else None
        for other in others:
            other_start = getdate(other.from_date)
            other_end = getdate(other.to_date) if other.to_date else None
            if (end is None or other_start <= end) and (other_end is None or other_end >= start):
                frappe.throw(
                    _(
                        "Assignment {0} of employee {1} overlaps this period. Put all projects of the period "
                        "into one assignment, or end the other one with a To Date."
                    ).format(get_link_to_form("Employee Project Assignment", other.name), self.employee),
                    title=_("Overlapping Assignment"),
                )
