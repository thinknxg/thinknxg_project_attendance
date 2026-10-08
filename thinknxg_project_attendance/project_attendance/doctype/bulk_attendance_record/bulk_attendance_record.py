import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, format_date, get_link_to_form, getdate, now_datetime, nowdate

from thinknxg_project_attendance.utils.common import (
    WORKED_STATUSES,
    currency_precision,
    daterange,
    get_approved_leaves,
    get_holiday_dates,
    get_month_range,
    get_salary_assignment,
    get_settings,
)
from thinknxg_project_attendance.utils.ledger import write_bulk_rows
from thinknxg_project_attendance.utils.overtime import get_overtime_rate

LINKED_DOCTYPES = ("Attendance", "Project Overtime", "Additional Salary")


class BulkAttendanceRecord(Document):
    # ------------------------------------------------------------------ lifecycle
    def validate(self):
        self._settings = get_settings()
        self.validate_period()
        self.validate_employee()
        self.validate_overlap()
        self.validate_header_project()
        self.validate_details()
        self.set_overtime_values()
        self.set_totals()
        self.title = f"{self.employee_name or self.employee} - {self.posting_month} {self.posting_year}"
        if self.docstatus == 0:
            self.status = "Draft"

    def before_submit(self):
        settings = get_settings()
        self.validate_existing_attendance()
        self.validate_payroll_not_processed()
        self.validate_overtime_setup(settings)
        self.status = "Submitted"

    def on_submit(self):
        settings = get_settings()
        additional_salary = self.create_additional_salary(settings)

        mute = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            for row in self.details:
                attendance = None
                overtime = None
                if row.status != "Holiday":
                    attendance = self.create_attendance(row)
                if flt(row.overtime_hours) > 0:
                    overtime = self.create_project_overtime(row, attendance, additional_salary, settings)
                row.db_set(
                    {"attendance": attendance, "project_overtime": overtime},
                    update_modified=False,
                )
        finally:
            frappe.flags.mute_messages = mute

        # the Project Attendance Ledger is the common costing layer for every attendance source
        write_bulk_rows(self)

    def before_cancel(self):
        self.ignore_linked_doctypes = LINKED_DOCTYPES
        self.validate_cancellation()

    def on_cancel(self):
        self.ignore_linked_doctypes = LINKED_DOCTYPES
        mute = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            # order matters: overtime links to attendance and additional salary
            for name in frappe.get_all(
                "Project Overtime", filters={"bulk_attendance_record": self.name, "docstatus": 1}, pluck="name"
            ):
                self._cancel_linked("Project Overtime", name)

            for name in frappe.get_all(
                "Additional Salary",
                filters={"ref_doctype": self.doctype, "ref_docname": self.name, "docstatus": 1},
                pluck="name",
            ):
                self._cancel_linked("Additional Salary", name)

            for name in frappe.get_all(
                "Attendance", filters={"nxg_bulk_attendance_record": self.name, "docstatus": 1}, pluck="name"
            ):
                self._cancel_linked("Attendance", name)
        finally:
            frappe.flags.mute_messages = mute

        frappe.db.delete("Project Attendance Ledger", {"bulk_attendance_record": self.name})
        self.db_set("status", "Cancelled")

    def on_trash(self):
        if self.docstatus == 1:
            frappe.throw(_("Submitted Bulk Attendance Record cannot be deleted. Cancel it first."))

    @staticmethod
    def _cancel_linked(doctype, name):
        doc = frappe.get_doc(doctype, name)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.cancel()

    # ------------------------------------------------------------------ header validations
    def validate_period(self):
        first, last = get_month_range(self.posting_month, self.posting_year)
        if not self.from_date:
            self.from_date = first
        if not self.to_date:
            self.to_date = last

        from_date, to_date = getdate(self.from_date), getdate(self.to_date)
        if from_date > to_date:
            frappe.throw(_("From Date cannot be after To Date."))
        if from_date < first or to_date > last:
            frappe.throw(
                _("From Date and To Date must be within {0} {1} ({2} to {3}).").format(
                    self.posting_month, self.posting_year, format_date(first), format_date(last)
                ),
                title=_("Dates Outside Posting Month"),
            )

    def validate_employee(self):
        emp = frappe.db.get_value(
            "Employee",
            self.employee,
            [
                "status",
                "company",
                "grade",
                "employee_name",
                "department",
                "date_of_joining",
                "relieving_date",
                "default_shift",
            ],
            as_dict=True,
        )
        if not emp:
            frappe.throw(_("Employee {0} does not exist.").format(self.employee))
        if emp.status != "Active":
            frappe.throw(
                _("Employee {0} is {1}. Attendance can only be recorded for active employees.").format(
                    frappe.bold(self.employee), frappe.bold(emp.status)
                ),
                title=_("Inactive Employee"),
            )

        self.employee_name = emp.employee_name
        self.department = emp.department
        if not self.company:
            self.company = emp.company
        if emp.company != self.company:
            frappe.throw(
                _("Employee {0} belongs to company {1}, not {2}.").format(
                    self.employee, emp.company, self.company
                )
            )
        if self.grade and emp.grade != self.grade:
            frappe.throw(
                _("Employee {0} is in grade {1}, not {2}.").format(
                    self.employee, frappe.bold(emp.grade or _("None")), frappe.bold(self.grade)
                )
            )
        if not self.grade:
            self.grade = emp.grade

        self._employee = emp

    def validate_overlap(self):
        overlapping = frappe.get_all(
            "Bulk Attendance Record",
            filters={
                "employee": self.employee,
                "docstatus": ["<", 2],
                "name": ["!=", self.name or "new"],
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
            },
            pluck="name",
            limit=1,
        )
        if overlapping:
            frappe.throw(
                _("Bulk Attendance Record {0} already covers this period for employee {1}.").format(
                    get_link_to_form("Bulk Attendance Record", overlapping[0]), frappe.bold(self.employee)
                ),
                title=_("Duplicate Bulk Attendance Record"),
            )

    def validate_header_project(self):
        if not cint(self.project_change_allowed) and not self.common_project:
            frappe.throw(_("Set the Common Project, or enable Project Change Allowed."))
        if self.common_project:
            self.validate_project(self.common_project, {})

    def validate_project(self, project, cache, row=None):
        if project not in cache:
            cache[project] = frappe.db.get_value(
                "Project", project, ["status", "is_active", "company"], as_dict=True
            )
        details = cache[project]
        prefix = _("Row {0}: ").format(row.idx) if row else ""
        if not details:
            frappe.throw(prefix + _("Project {0} does not exist.").format(project))
        if details.status == "Cancelled" or details.is_active == "No":
            frappe.throw(
                prefix + _("Project {0} is cancelled or inactive.").format(frappe.bold(project)),
                title=_("Invalid Project"),
            )
        if details.company and details.company != self.company:
            frappe.throw(
                prefix
                + _("Project {0} belongs to company {1}.").format(frappe.bold(project), details.company),
                title=_("Invalid Project"),
            )

    # ------------------------------------------------------------------ row validations
    def validate_details(self):
        if not self.details:
            frappe.throw(_("No attendance days found. Use Generate Days to fill the table."))

        settings = self._settings
        emp = self._employee
        from_date, to_date = getdate(self.from_date), getdate(self.to_date)
        today = getdate(nowdate())
        joining = getdate(emp.date_of_joining) if emp.date_of_joining else None
        relieving = getdate(emp.relieving_date) if emp.relieving_date else None
        normal_hours = flt(settings.normal_working_hours) or 8.0
        max_ot = flt(settings.max_overtime_hours_per_day)

        holidays = get_holiday_dates(self.employee, self.company, from_date, to_date)
        leaves = get_approved_leaves(self.employee, from_date, to_date)
        project_cache = {}
        seen = set()

        for row in self.details:
            if not row.day:
                frappe.throw(_("Row {0}: Date is mandatory.").format(row.idx))
            day = getdate(row.day)
            label = format_date(day)

            if day < from_date or day > to_date:
                frappe.throw(
                    _("Row {0}: {1} is outside the period {2} to {3}.").format(
                        row.idx, label, format_date(from_date), format_date(to_date)
                    )
                )
            if day in seen:
                frappe.throw(_("Row {0}: {1} is entered more than once.").format(row.idx, label))
            seen.add(day)

            row.weekday = day.strftime("%A")
            row.is_holiday = 1 if day in holidays else 0
            if not row.status:
                frappe.throw(_("Row {0}: Status is mandatory.").format(row.idx))

            if joining and day < joining:
                frappe.throw(
                    _("Row {0}: {1} is before the joining date {2}.").format(
                        row.idx, label, format_date(joining)
                    )
                )
            if relieving and day > relieving:
                frappe.throw(
                    _("Row {0}: {1} is after the relieving date {2}.").format(
                        row.idx, label, format_date(relieving)
                    )
                )
            if (
                day > today
                and row.status not in ("On Leave", "Holiday")
                and not cint(settings.allow_future_dates)
            ):
                frappe.throw(
                    _("Row {0}: attendance cannot be marked for the future date {1}.").format(row.idx, label)
                )

            # project control
            if not cint(self.project_change_allowed):
                row.project = self.common_project
            elif not row.project:
                row.project = self.common_project

            worked = row.status in WORKED_STATUSES
            if worked and not row.project:
                frappe.throw(_("Row {0}: Project is mandatory for status {1}.").format(row.idx, row.status))
            if row.project:
                self.validate_project(row.project, project_cache, row)

            # overtime and working hours
            row.overtime_hours = flt(row.overtime_hours)
            if row.overtime_hours < 0:
                frappe.throw(_("Row {0}: Overtime Hours cannot be negative.").format(row.idx))
            if row.overtime_hours and not worked:
                frappe.throw(
                    _("Row {0}: Overtime Hours are not allowed for status {1}.").format(row.idx, row.status)
                )
            if max_ot and row.overtime_hours > max_ot:
                frappe.throw(
                    _("Row {0}: Overtime Hours {1} exceed the maximum of {2} per day.").format(
                        row.idx, row.overtime_hours, max_ot
                    )
                )

            if worked:
                if not flt(row.working_hours):
                    row.working_hours = normal_hours / 2 if row.status == "Half Day" else normal_hours
                if flt(row.working_hours) + row.overtime_hours > 24:
                    frappe.throw(
                        _("Row {0}: Working Hours plus Overtime Hours cannot exceed 24.").format(row.idx)
                    )
                if not row.shift and emp.default_shift:
                    row.shift = emp.default_shift
            else:
                row.working_hours = 0

            # leave control
            if row.status == "Holiday":
                row.leave_type = None
                row.leave_application = None
                continue

            leave = leaves.get(day)
            if leave:
                expected = "Half Day" if leave.half_day else "On Leave"
                if row.status != expected:
                    frappe.throw(
                        _(
                            "Row {0}: an approved Leave Application {1} exists for {2}. Status must be {3}."
                        ).format(
                            row.idx,
                            get_link_to_form("Leave Application", leave.name),
                            label,
                            frappe.bold(expected),
                        ),
                        title=_("Invalid Leave Date"),
                    )
                row.leave_type = leave.leave_type
                row.leave_application = leave.name
            else:
                row.leave_application = None
                if row.status == "On Leave":
                    if cint(settings.require_leave_application):
                        frappe.throw(
                            _("Row {0}: no approved Leave Application found for {1}.").format(row.idx, label),
                            title=_("Invalid Leave Date"),
                        )
                    if not row.leave_type:
                        frappe.throw(
                            _("Row {0}: select a Leave Type for the On Leave day {1}.").format(row.idx, label),
                            title=_("Invalid Leave Date"),
                        )
                elif row.status != "Half Day":
                    row.leave_type = None

    def set_overtime_values(self):
        precision = currency_precision()
        cache = {}
        missing_rate = False
        for row in self.details:
            if flt(row.overtime_hours) > 0:
                rate = get_overtime_rate(
                    self.employee,
                    row.day,
                    is_holiday=cint(row.is_holiday),
                    grade=self.grade,
                    settings=self._settings,
                    cache=cache,
                )
                row.overtime_rate = flt(rate, 6)
                row.overtime_amount = flt(flt(rate) * flt(row.overtime_hours), precision)
                if not rate:
                    missing_rate = True
            else:
                row.overtime_rate = 0
                row.overtime_amount = 0

        if missing_rate and self.docstatus == 0:
            frappe.msgprint(
                _(
                    "The overtime rate could not be determined for employee {0} (method: {1}). "
                    "It must be available before this record can be submitted."
                ).format(self.employee, self._settings.overtime_calculation_method),
                indicator="orange",
                alert=True,
            )

    def set_totals(self):
        counts = {"Present": 0, "Half Day": 0, "Work From Home": 0, "Absent": 0, "On Leave": 0, "Holiday": 0}
        hours = overtime = amount = 0.0
        for row in self.details:
            counts[row.status] = counts.get(row.status, 0) + 1
            hours += flt(row.working_hours)
            overtime += flt(row.overtime_hours)
            amount += flt(row.overtime_amount)

        self.total_present = counts["Present"]
        self.total_half_day = counts["Half Day"]
        self.total_wfh = counts["Work From Home"]
        self.total_absent = counts["Absent"]
        self.total_leave = counts["On Leave"]
        self.total_holidays = counts["Holiday"]
        self.total_working_hours = hours
        self.total_overtime_hours = overtime
        self.total_overtime_amount = flt(amount, currency_precision())

    # ------------------------------------------------------------------ submit validations
    def validate_existing_attendance(self):
        dates = [getdate(row.day) for row in self.details if row.status != "Holiday"]
        if not dates:
            return
        existing = frappe.get_all(
            "Attendance",
            filters={
                "employee": self.employee,
                "docstatus": ["<", 2],
                "attendance_date": ["in", dates],
            },
            fields=["name", "attendance_date"],
            order_by="attendance_date",
        )
        if existing:
            rows = "".join(
                f"<li>{format_date(d.attendance_date)}: {get_link_to_form('Attendance', d.name)}</li>"
                for d in existing[:15]
            )
            more = _("... and {0} more").format(len(existing) - 15) if len(existing) > 15 else ""
            frappe.throw(
                _("Attendance is already marked for employee {0} on:").format(frappe.bold(self.employee))
                + f"<ul>{rows}</ul>{more}"
                + _(
                    "These days are already covered (for example by Auto Attendance from Employee Checkins). "
                    "A day can have only one costing source: remove the rows from this record or cancel the Attendance."
                ),
                title=_("Duplicate Attendance"),
            )

    def validate_payroll_not_processed(self):
        slip = frappe.db.get_value(
            "Salary Slip",
            {
                "employee": self.employee,
                "docstatus": 1,
                "start_date": ["<=", self.to_date],
                "end_date": [">=", self.from_date],
            },
            "name",
        )
        if slip:
            frappe.throw(
                _("Salary Slip {0} is already submitted for this period. Cancel it before recording attendance.").format(
                    get_link_to_form("Salary Slip", slip)
                ),
                title=_("Payroll Already Processed"),
            )

    def validate_overtime_setup(self, settings):
        if flt(self.total_overtime_hours) <= 0:
            return
        for row in self.details:
            if flt(row.overtime_hours) > 0 and not flt(row.overtime_rate):
                frappe.throw(
                    _(
                        "Row {0}: the overtime rate is zero. Check the overtime method in {1} and the "
                        "Salary Structure Assignment / hourly rate of employee {2}."
                    ).format(
                        row.idx,
                        get_link_to_form("Project Attendance Settings", "Project Attendance Settings"),
                        self.employee,
                    ),
                    title=_("Overtime Rate Missing"),
                )
        if cint(settings.create_additional_salary):
            component = settings.overtime_salary_component
            if not component:
                frappe.throw(
                    _("Set the Payroll Component for Overtime in {0}.").format(
                        get_link_to_form("Project Attendance Settings", "Project Attendance Settings")
                    )
                )
            if frappe.db.get_value("Salary Component", component, "type") != "Earning":
                frappe.throw(_("Salary Component {0} must be of type Earning.").format(component))

    def validate_cancellation(self):
        paid = frappe.db.get_value(
            "Project Overtime",
            {"bulk_attendance_record": self.name, "docstatus": 1, "salary_slip": ["is", "set"]},
            "salary_slip",
        )
        if paid:
            frappe.throw(
                _("Overtime of this record is already paid in Salary Slip {0}. Cancel the Salary Slip first.").format(
                    get_link_to_form("Salary Slip", paid)
                ),
                title=_("Payroll Already Processed"),
            )

        if self.additional_salary:
            slip = frappe.db.get_value(
                "Salary Detail",
                {
                    "additional_salary": self.additional_salary,
                    "parenttype": "Salary Slip",
                    "docstatus": ["<", 2],
                },
                "parent",
            )
            if slip:
                frappe.throw(
                    _(
                        "Additional Salary {0} is already used in Salary Slip {1}. Cancel or delete the Salary Slip first."
                    ).format(self.additional_salary, get_link_to_form("Salary Slip", slip)),
                    title=_("Payroll Already Processed"),
                )

        slip = frappe.db.get_value(
            "Salary Slip",
            {
                "employee": self.employee,
                "docstatus": 1,
                "start_date": ["<=", self.to_date],
                "end_date": [">=", self.from_date],
            },
            "name",
        )
        if slip:
            frappe.throw(
                _("Salary Slip {0} is submitted for this period. Cancel it first.").format(
                    get_link_to_form("Salary Slip", slip)
                ),
                title=_("Payroll Already Processed"),
            )

    # ------------------------------------------------------------------ document creation
    def create_attendance(self, row):
        attendance = frappe.new_doc("Attendance")
        attendance.update(
            {
                "employee": self.employee,
                "employee_name": self.employee_name,
                "company": self.company,
                "department": self.department,
                "attendance_date": row.day,
                "status": row.status,
                "shift": row.shift,
                "working_hours": flt(row.working_hours),
                "leave_type": row.leave_type if row.status in ("On Leave", "Half Day") else None,
                "leave_application": row.leave_application,
                "nxg_project": row.project,
                "nxg_overtime_hours": flt(row.overtime_hours),
                "nxg_bulk_attendance_record": self.name,
            }
        )
        if row.status == "Half Day" and attendance.meta.has_field("half_day_status"):
            # the other half: present if there is a leave application, HRMS sets Absent otherwise
            attendance.half_day_status = "Present" if row.leave_application else "Absent"
        attendance.flags.ignore_permissions = True
        attendance.insert()
        attendance.submit()
        return attendance.name

    def create_project_overtime(self, row, attendance, additional_salary, settings):
        overtime = frappe.new_doc("Project Overtime")
        overtime.update(
            {
                "employee": self.employee,
                "employee_name": self.employee_name,
                "department": self.department,
                "company": self.company,
                "attendance_date": row.day,
                "project": row.project,
                "source": "Bulk Attendance",
                "is_holiday": cint(row.is_holiday),
                "overtime_hours": flt(row.overtime_hours),
                # overtime typed on the record is approved by submitting the record
                "approval_status": "Approved",
                "approved_hours": flt(row.overtime_hours),
                "approved_by": frappe.session.user,
                "approved_on": now_datetime(),
                "approval_remarks": "Approved with the Bulk Attendance Record",
                "overtime_rate": flt(row.overtime_rate),
                "calculation_method": settings.overtime_calculation_method,
                "bulk_attendance_record": self.name,
                "attendance": attendance,
                "additional_salary": additional_salary,
            }
        )
        overtime.flags.ignore_permissions = True
        overtime.insert()
        overtime.submit()
        return overtime.name

    def create_additional_salary(self, settings):
        amount = flt(self.total_overtime_amount, currency_precision())
        if amount <= 0 or not cint(settings.create_additional_salary):
            return None

        assignment = get_salary_assignment(self.employee, self.to_date)
        currency = (assignment.currency if assignment else None) or frappe.get_cached_value(
            "Company", self.company, "default_currency"
        )

        additional_salary = frappe.new_doc("Additional Salary")
        additional_salary.update(
            {
                "employee": self.employee,
                "employee_name": self.employee_name,
                "department": self.department,
                "company": self.company,
                "salary_component": settings.overtime_salary_component,
                "amount": amount,
                "currency": currency,
                "payroll_date": self.to_date,
                "is_recurring": 0,
                "overwrite_salary_structure_amount": 0,
                "ref_doctype": self.doctype,
                "ref_docname": self.name,
            }
        )
        additional_salary.flags.ignore_permissions = True
        additional_salary.insert()
        additional_salary.submit()
        self.db_set("additional_salary", additional_salary.name, update_modified=False)
        return additional_salary.name

    # ------------------------------------------------------------------ client actions
    @frappe.whitelist()
    def generate_days(self):
        """(Re)build the daily table for the period, keeping what was already entered."""
        if self.docstatus != 0:
            frappe.throw(_("Days can only be generated on a draft record."))
        if not self.employee:
            frappe.throw(_("Select an Employee first."))

        self._settings = get_settings()
        self.validate_period()
        self.validate_employee()
        fill_days(self, self._settings, self._employee)
        self.set_totals()


def fill_days(doc, settings, emp):
    from_date, to_date = getdate(doc.from_date), getdate(doc.to_date)
    today = getdate(nowdate())
    joining = getdate(emp.date_of_joining) if emp.date_of_joining else None
    relieving = getdate(emp.relieving_date) if emp.relieving_date else None
    normal_hours = flt(settings.normal_working_hours) or 8.0

    holidays = get_holiday_dates(doc.employee, doc.company, from_date, to_date)
    leaves = get_approved_leaves(doc.employee, from_date, to_date)
    existing = {getdate(row.day): row.as_dict() for row in doc.get("details") or [] if row.day}

    rows = []
    skipped_future = False
    for day in daterange(from_date, to_date):
        if (joining and day < joining) or (relieving and day > relieving):
            continue

        if day in existing:
            old = existing[day]
            row = {
                key: old.get(key)
                for key in (
                    "status",
                    "project",
                    "shift",
                    "overtime_hours",
                    "working_hours",
                    "leave_type",
                    "leave_application",
                    "remarks",
                )
            }
        else:
            leave = leaves.get(day)
            if day in holidays:
                status = "Holiday"
            elif leave:
                status = "Half Day" if leave.half_day else "On Leave"
            elif day > today and not cint(settings.allow_future_dates):
                skipped_future = True
                continue
            else:
                status = "Present"

            worked = status in WORKED_STATUSES
            row = {
                "status": status,
                "project": doc.common_project,
                "shift": emp.default_shift if worked else None,
                "overtime_hours": 0,
                "working_hours": (normal_hours / 2 if status == "Half Day" else normal_hours) if worked else 0,
                "leave_type": leave.leave_type if leave else None,
                "leave_application": leave.name if leave else None,
            }

        if not cint(doc.project_change_allowed) and doc.common_project:
            row["project"] = doc.common_project
        row.update({"day": day, "weekday": day.strftime("%A"), "is_holiday": 1 if day in holidays else 0})
        rows.append(row)

    doc.set("details", [])
    for row in rows:
        doc.append("details", row)

    if skipped_future:
        frappe.msgprint(
            _("Future working days were skipped. Regenerate later or shorten the To Date."),
            indicator="blue",
            alert=True,
        )
