"""Project Attendance Ledger: the normalised layer between attendance sources and project costing.

Bulk Attendance Records and Attendance created by HRMS (Auto Attendance from Employee Checkins,
manual Attendance, Attendance Requests ...) both write here. Payroll allocation, overtime and the
project reports read only from here, so there is one costing engine for every source.
"""
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from thinknxg_project_attendance.utils.common import (
    WORKED_STATUSES,
    get_holiday_dates,
    get_payroll_cost_center,
    get_settings,
)

PAL = "Project Attendance Ledger"
ALTERNATING = "Alternating entries as IN and OUT during the same shift"
FIRST_LAST = "First Check-in and Last Check-out"
SOURCE_CHECKIN = "Employee Checkin"
SOURCE_BULK = "Bulk Attendance"
SOURCE_ATTENDANCE = "Attendance"

ATTENDANCE_FIELDS = [
    "name",
    "employee",
    "employee_name",
    "company",
    "department",
    "attendance_date",
    "status",
    "shift",
    "working_hours",
    "in_time",
    "out_time",
    "docstatus",
    "nxg_project",
    "nxg_bulk_attendance_record",
]


# ---------------------------------------------------------------------------- pure helpers
def hours_between(start, end):
    return max((end - start).total_seconds(), 0.0) / 3600.0


def build_intervals(logs, check_in_out_type=None, calc_type=None):
    """Turn chronological checkin logs into (start_log, end_log) work intervals.

    Mirrors HRMS `calculate_working_hours`, so the interval hours add up to the working hours of
    the Attendance. With 'First Check-in and Last Check-out' every log starts a new interval,
    which is what lets an employee switch project during the day.
    """
    logs = list(logs)
    if len(logs) < 2:
        return []

    alternating = (check_in_out_type or ALTERNATING) == ALTERNATING
    first_last = (calc_type or FIRST_LAST) == FIRST_LAST
    pairs = []

    if alternating:
        step = 1 if first_last else 2
        pairs = [(logs[i], logs[i + 1]) for i in range(0, len(logs) - 1, step)]
    elif first_last:
        first_in = next((i for i, log in enumerate(logs) if log.get("log_type") == "IN"), None)
        last_out = next((i for i in range(len(logs) - 1, -1, -1) if logs[i].get("log_type") == "OUT"), None)
        if first_in is None or last_out is None or last_out <= first_in:
            return []
        span = logs[first_in : last_out + 1]
        pairs = [(span[i], span[i + 1]) for i in range(len(span) - 1)]
    else:
        in_log = None
        for log in logs:
            if in_log is None:
                if log.get("log_type") == "IN":
                    in_log = log
            elif log.get("log_type") == "OUT":
                pairs.append((in_log, log))
                in_log = None

    return [pair for pair in pairs if pair[1]["time"] > pair[0]["time"]]


def split_day(pieces, standard_hours=None, max_overtime=0, method="Chronological"):
    """Set `regular` and `overtime` on each piece (dicts with `hours`, in chronological order).

    standard_hours None means no overtime at all. `max_overtime` caps the overtime of the day;
    hours beyond the cap are neither regular nor overtime.
    """
    total = sum(flt(p["hours"]) for p in pieces)
    if standard_hours is None:
        regular_total, overtime_total = total, 0.0
    else:
        regular_total = min(total, flt(standard_hours))
        overtime_total = max(total - flt(standard_hours), 0.0)
        if flt(max_overtime) and overtime_total > flt(max_overtime):
            overtime_total = flt(max_overtime)

    if method == "Proportional":
        for piece in pieces:
            share = flt(piece["hours"]) / total if total else 0.0
            piece["regular"] = round(regular_total * share, 4)
            piece["overtime"] = round(overtime_total * share, 4)
        return pieces

    remaining_regular, remaining_overtime = regular_total, overtime_total
    for piece in pieces:
        hours = flt(piece["hours"])
        regular = min(hours, remaining_regular)
        remaining_regular -= regular
        overtime = min(hours - regular, remaining_overtime)
        remaining_overtime -= overtime
        piece["regular"] = round(regular, 4)
        piece["overtime"] = round(overtime, 4)
    return pieces


# ---------------------------------------------------------------------------- project resolution
class ProjectResolver:
    """Resolves the project of an interval.

    Priority: project on the Employee Checkin (typed, API or device mapping) > Employee Project
    Assignment > default project of the Employee > default project of the Department >
    'Project for Unallocated Hours' of the settings > Unallocated.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._assignments = {}
        self._defaults = {}

    def assignments(self, employee, on_date):
        """Project rows (project, allocation %, primary, override flag) of the assignments active on a date."""
        key = (employee, on_date)
        if key not in self._assignments:
            parents = frappe.get_all(
                "Employee Project Assignment",
                filters={"employee": employee, "disabled": 0, "from_date": ["<=", on_date]},
                fields=["name", "to_date", "allow_checkin_override"],
                order_by="from_date desc",
            )
            parents = {p.name: p for p in parents if not p.to_date or getdate(p.to_date) >= on_date}
            rows = []
            if parents:
                for row in frappe.get_all(
                    "Employee Project Allocation",
                    filters={"parent": ["in", list(parents)], "parenttype": "Employee Project Assignment"},
                    fields=["parent", "project", "allocation_percent", "is_primary"],
                    order_by="is_primary desc, idx asc",
                ):
                    row.allow_checkin_override = parents[row.parent].allow_checkin_override
                    rows.append(row)
            self._assignments[key] = rows
        return self._assignments[key]

    def defaults(self, employee):
        if employee not in self._defaults:
            project, department = frappe.db.get_value(
                "Employee", employee, ["nxg_default_project", "department"]
            ) or (None, None)
            label = "Employee Default"
            if not project and department:
                project = frappe.db.get_value("Department", department, "nxg_default_project")
                label = "Department Default"
            self._defaults[employee] = (project, label) if project else (None, None)
        return self._defaults[employee]

    def resolve(self, employee, on_date, hint_project=None, hint_label=None, is_override=False):
        """Return a list of (project or None, weight, label); the weights add up to 1."""
        on_date = getdate(on_date)
        assignments = self.assignments(employee, on_date)
        locked = bool(assignments) and not any(cint(a.allow_checkin_override) for a in assignments)

        if hint_project and (not locked or is_override):
            return [(hint_project, 1.0, hint_label or "Checkin")]

        if assignments:
            if len(assignments) == 1:
                return [(assignments[0].project, 1.0, "Assignment")]
            weighted = [a for a in assignments if flt(a.allocation_percent) > 0]
            if weighted:
                total = sum(flt(a.allocation_percent) for a in weighted)
                merged = defaultdict(float)
                for a in weighted:
                    merged[a.project] += flt(a.allocation_percent) / total
                return [(project, weight, "Assignment") for project, weight in merged.items()]
            return [(assignments[0].project, 1.0, "Assignment")]

        project, label = self.defaults(employee)
        if project:
            return [(project, 1.0, label)]

        if self.settings.unallocated_project:
            return [(self.settings.unallocated_project, 1.0, "Unallocated Project")]
        return [(None, 1.0, "Unallocated")]


# ---------------------------------------------------------------------------- writers
def _insert_row(values):
    doc = frappe.new_doc(PAL)
    doc.update(values)
    doc.is_unallocated = 0 if doc.project else 1
    doc.flags.ignore_permissions = True
    doc.flags.ignore_links = True
    doc.insert()
    return doc.name


def write_bulk_rows(bar):
    """Ledger rows of a submitted Bulk Attendance Record: one per worked day."""
    cost_centers = {}
    payroll_cost_center = get_payroll_cost_center(bar.employee, bar.company)
    for row in bar.details:
        if row.status not in WORKED_STATUSES:
            continue
        if row.project not in cost_centers:
            cost_centers[row.project] = (
                frappe.db.get_value("Project", row.project, "cost_center") or payroll_cost_center
            )
        _insert_row(
            {
                "employee": bar.employee,
                "employee_name": bar.employee_name,
                "department": bar.department,
                "company": bar.company,
                "attendance_date": row.day,
                "attendance_status": row.status,
                "shift": row.shift,
                "is_holiday": cint(row.is_holiday),
                "project": row.project,
                "project_resolution": "Bulk Attendance",
                "cost_center": cost_centers[row.project],
                "regular_hours": flt(row.working_hours),
                "overtime_hours": flt(row.overtime_hours),
                "working_hours": flt(row.working_hours) + flt(row.overtime_hours),
                "day_fraction": 1,
                "source": SOURCE_BULK,
                "attendance": row.attendance,
                "bulk_attendance_record": bar.name,
            }
        )


def get_checkins(att):
    fields = ["name", "time", "log_type", "device_id", "nxg_project", "nxg_project_source", "nxg_is_project_override"]
    logs = frappe.get_all(
        "Employee Checkin", filters={"attendance": att.name}, fields=fields, order_by="time asc"
    )
    if logs or not (att.shift and (att.in_time or att.out_time)):
        return logs

    # HRMS links the checkins to the Attendance only after it is submitted; during on_submit the
    # logs of the same employee and shift day are the ones being processed.
    day = getdate(att.attendance_date)
    return frappe.get_all(
        "Employee Checkin",
        filters=[
            ["employee", "=", att.employee],
            ["shift", "=", att.shift],
            ["skip_auto_attendance", "=", 0],
            ["attendance", "is", "not set"],
            ["shift_start", ">=", f"{day} 00:00:00"],
            ["shift_start", "<=", f"{day} 23:59:59"],
        ],
        fields=fields,
        order_by="time asc",
    )


def _log_hint(log):
    if not log.get("nxg_project"):
        return None
    return (log.nxg_project, log.get("nxg_project_source") or "Checkin", cint(log.get("nxg_is_project_override")))


def get_standard_hours(att, settings, is_holiday):
    """Hours of the day paid as regular time; None = do not calculate overtime."""
    if not cint(settings.checkin_overtime):
        return None
    if is_holiday and cint(settings.holiday_hours_as_overtime):
        return 0.0
    if (settings.standard_hours_source or "").startswith("Shift") and att.shift:
        start, end = frappe.get_cached_value("Shift Type", att.shift, ["start_time", "end_time"])
        if start is not None and end is not None:
            seconds = (end - start).total_seconds()
            if seconds <= 0:
                seconds += 24 * 3600
            return seconds / 3600.0
    return flt(settings.normal_working_hours) or 8.0


def is_costed(attendance):
    return bool(frappe.db.exists(PAL, {"attendance": attendance, "salary_slip": ["is", "set"]}))


def release_attendance(attendance):
    """Remove the ledger rows and the unpaid checkin overtime of an Attendance."""
    from thinknxg_project_attendance.utils.overtime import release_additional_salary

    slip = frappe.db.get_value(PAL, {"attendance": attendance, "salary_slip": ["is", "set"]}, "salary_slip")
    if slip:
        frappe.throw(
            _("Attendance {0} is already costed in Salary Slip {1}. Cancel the Salary Slip first.").format(
                attendance, slip
            ),
            title=_("Payroll Already Processed"),
        )

    overtime = frappe.get_all(
        "Project Overtime",
        filters={"attendance": attendance, "docstatus": 1, "bulk_attendance_record": ["is", "not set"]},
        fields=["name", "salary_slip", "additional_salary"],
    )
    for record in overtime:
        if record.salary_slip:
            frappe.throw(
                _("Overtime {0} is already paid in Salary Slip {1}. Cancel the Salary Slip first.").format(
                    record.name, record.salary_slip
                ),
                title=_("Payroll Already Processed"),
            )
    for additional_salary in {r.additional_salary for r in overtime if r.additional_salary}:
        release_additional_salary(additional_salary)
    for record in overtime:
        doc = frappe.get_doc("Project Overtime", record.name)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.cancel()

    frappe.db.delete(PAL, {"attendance": attendance})


def process_attendance(attendance, settings=None, resolver=None):
    """(Re)build the ledger rows and overtime of one Attendance that is not from a Bulk Attendance Record.

    Returns a short status word: processed / skipped / costed / duplicate.
    """
    from thinknxg_project_attendance.utils.approval import initial_approval
    from thinknxg_project_attendance.utils.overtime import get_overtime_rate

    settings = settings or get_settings()
    att = attendance
    if isinstance(attendance, str):
        att = frappe.db.get_value("Attendance", attendance, ATTENDANCE_FIELDS, as_dict=True)
    if not att or cint(att.get("docstatus")) != 1 or att.get("nxg_bulk_attendance_record"):
        return "skipped"
    if not cint(settings.enable_checkin_costing):
        return "skipped"
    if is_costed(att.name):
        return "costed"

    # approvals already given survive a rebuild as long as the overtime of that project is unchanged
    previous_approvals = {
        (row.project or ""): row
        for row in frappe.get_all(
            "Project Overtime",
            filters={"attendance": att.name, "docstatus": 1, "bulk_attendance_record": ["is", "not set"]},
            fields=["project", "overtime_hours", "approval_status", "approved_hours", "approved_by", "approved_on", "approval_remarks"],
        )
        if row.approval_status in ("Approved", "Rejected")
    }

    release_attendance(att.name)
    if att.status not in WORKED_STATUSES:
        return "skipped"

    day = getdate(att.attendance_date)
    if frappe.db.exists(PAL, {"employee": att.employee, "attendance_date": day, "source": SOURCE_BULK}):
        # one costing source per employee and day: the Bulk Attendance Record wins
        frappe.log_error(
            title="Project Attendance: duplicate attendance source",
            message=f"Attendance {att.name} ({att.employee}, {day}) was not written to the Project "
            "Attendance Ledger because a Bulk Attendance Record already covers that day.",
        )
        return "duplicate"

    resolver = resolver or ProjectResolver(settings)
    is_holiday = day in get_holiday_dates(att.employee, att.company, day, day)
    logs = get_checkins(att)
    pieces = []

    if logs:
        check_type = calc_type = None
        if att.shift:
            check_type, calc_type = frappe.get_cached_value(
                "Shift Type", att.shift, ["determine_check_in_and_check_out", "working_hours_calculation_based_on"]
            )
        carried = None  # project last declared on a log, carried forward to logs without one
        for start_log, end_log in build_intervals(logs, check_type, calc_type):
            hint = _log_hint(start_log) or carried or _log_hint(end_log)
            if hint:
                carried = hint

            hours = hours_between(start_log.time, end_log.time)
            hint = hint or (None, None, 0)
            for project, weight, label in resolver.resolve(att.employee, day, hint[0], hint[1], hint[2]):
                pieces.append(
                    {
                        "project": project,
                        "label": label,
                        "hours": hours * weight,
                        "in_time": start_log.time,
                        "out_time": end_log.time,
                        "checkin_log": start_log.name,
                        "checkout_log": end_log.name,
                    }
                )

    source = SOURCE_CHECKIN if logs else SOURCE_ATTENDANCE
    if pieces and sum(p["hours"] for p in pieces) > 0:
        split_day(
            pieces,
            get_standard_hours(att, settings, is_holiday),
            flt(settings.max_overtime_hours_per_day),
            settings.overtime_allocation_method or "Chronological",
        )
        overtime_total = sum(p["overtime"] for p in pieces)
        if overtime_total and overtime_total * 60 < cint(settings.minimum_overtime_minutes):
            split_day(pieces, None)
    else:
        # no usable intervals (manual attendance, a single log ...): one row for the whole day
        equivalent = 0.5 if att.status == "Half Day" else 1.0
        hours = flt(att.working_hours) or (flt(settings.normal_working_hours) or 8.0) * equivalent
        hint_project = att.get("nxg_project") or next((l.nxg_project for l in logs if l.get("nxg_project")), None)
        pieces = []
        for project, weight, label in resolver.resolve(
            att.employee, day, hint_project, "Attendance" if att.get("nxg_project") else "Checkin"
        ):
            pieces.append(
                {"project": project, "label": label, "hours": hours * weight, "in_time": att.in_time, "out_time": att.out_time}
            )
        split_day(pieces, None)

    total_hours = sum(p["hours"] for p in pieces)
    payroll_cost_center = get_payroll_cost_center(att.employee, att.company)
    cost_centers = {}
    overtime_by_project = defaultdict(float)

    for piece in pieces:
        project = piece["project"]
        if project not in cost_centers:
            cost_centers[project] = (
                frappe.db.get_value("Project", project, "cost_center") if project else None
            ) or payroll_cost_center
        if piece["overtime"]:
            overtime_by_project[project or ""] += piece["overtime"]
        _insert_row(
            {
                "employee": att.employee,
                "employee_name": att.employee_name,
                "department": att.department,
                "company": att.company,
                "attendance_date": day,
                "attendance_status": att.status,
                "shift": att.shift,
                "is_holiday": 1 if is_holiday else 0,
                "project": project,
                "project_resolution": piece["label"],
                "cost_center": cost_centers[project],
                "in_time": piece.get("in_time"),
                "out_time": piece.get("out_time"),
                "working_hours": round(piece["hours"], 4),
                "regular_hours": piece["regular"],
                "overtime_hours": piece["overtime"],
                "day_fraction": round(piece["hours"] / total_hours, 4) if total_hours else round(1.0 / len(pieces), 4),
                "source": source,
                "attendance": att.name,
                "checkin_log": piece.get("checkin_log"),
                "checkout_log": piece.get("checkout_log"),
            }
        )

    rate_cache = {}
    for project, hours in overtime_by_project.items():
        hours = round(hours, 2)
        if hours <= 0:
            continue
        overtime = frappe.new_doc("Project Overtime")
        overtime.update(
            {
                "employee": att.employee,
                "employee_name": att.employee_name,
                "department": att.department,
                "company": att.company,
                "attendance_date": day,
                "project": project or None,
                "source": SOURCE_CHECKIN,
                "is_holiday": 1 if is_holiday else 0,
                "overtime_hours": hours,
                "overtime_rate": flt(
                    get_overtime_rate(att.employee, day, is_holiday=is_holiday, settings=settings, cache=rate_cache), 6
                ),
                "calculation_method": settings.overtime_calculation_method,
                "attendance": att.name,
            }
        )
        previous = previous_approvals.get(project or "")
        if previous and abs(flt(previous.overtime_hours) - hours) < 0.01:
            overtime.update(
                {
                    "approval_status": previous.approval_status,
                    "approved_hours": min(flt(previous.approved_hours), hours),
                    "approved_by": previous.approved_by,
                    "approved_on": previous.approved_on,
                    "approval_remarks": previous.approval_remarks,
                }
            )
        else:
            overtime.update(initial_approval(settings))
        overtime.flags.ignore_permissions = True
        overtime.insert()
        overtime.submit()

    return "processed"


def safe_process(attendance, settings=None, resolver=None):
    """process_attendance that never raises: HRMS Auto Attendance must not fail because of costing."""
    name = attendance if isinstance(attendance, str) else attendance.get("name")
    try:
        frappe.db.savepoint("nxg_project_ledger")
        return process_attendance(attendance, settings, resolver)
    except Exception:
        try:
            frappe.db.rollback(save_point="nxg_project_ledger")
        except Exception:
            pass
        frappe.log_error(
            title=f"Project Attendance Ledger failed for {name}", message=frappe.get_traceback()
        )
        return "failed"


# ---------------------------------------------------------------------------- maintenance
def _rebuild(from_date, to_date, company=None, employee=None):
    filters = {
        "docstatus": 1,
        "attendance_date": ["between", [from_date, to_date]],
        "nxg_bulk_attendance_record": ["is", "not set"],
    }
    if company:
        filters["company"] = company
    if employee:
        filters["employee"] = employee

    settings = get_settings()
    resolver = ProjectResolver(settings)
    counts = defaultdict(int)
    for att in frappe.get_all("Attendance", filters=filters, fields=ATTENDANCE_FIELDS, order_by="attendance_date"):
        counts[safe_process(att, settings, resolver)] += 1
    return dict(counts)


@frappe.whitelist()
def rebuild_ledger(from_date, to_date, company=None, employee=None):
    """Rebuild the ledger from Attendance for a period. Days already costed in a Salary Slip are kept."""
    frappe.only_for(("HR Manager", "System Manager"))
    if getdate(from_date) > getdate(to_date):
        frappe.throw(_("From Date cannot be after To Date."))
    if not employee and (getdate(to_date) - getdate(from_date)).days > 31:
        frappe.enqueue(
            "thinknxg_project_attendance.utils.ledger._rebuild",
            queue="long",
            from_date=from_date,
            to_date=to_date,
            company=company,
            employee=employee,
        )
        return {"queued": 1}
    return _rebuild(from_date, to_date, company, employee)


def reconcile_ledger():
    """Daily: process attendance that has no ledger rows yet, or whose checkins arrived later."""
    settings = get_settings()
    if not cint(settings.enable_checkin_costing):
        return

    start = add_days(nowdate(), -45)
    attendance = frappe.get_all(
        "Attendance",
        filters={
            "docstatus": 1,
            "attendance_date": [">=", start],
            "status": ["in", list(WORKED_STATUSES)],
            "nxg_bulk_attendance_record": ["is", "not set"],
        },
        fields=ATTENDANCE_FIELDS,
    )
    if not attendance:
        return

    names = [a.name for a in attendance]
    ledger_source = {}
    for row in frappe.get_all(PAL, filters={"attendance": ["in", names]}, fields=["attendance", "source"]):
        ledger_source[row.attendance] = row.source
    with_checkins = set(
        frappe.get_all("Employee Checkin", filters={"attendance": ["in", names]}, pluck="attendance", distinct=True)
    )

    resolver = ProjectResolver(settings)
    for index, att in enumerate(attendance):
        source = ledger_source.get(att.name)
        if source is None or (source == SOURCE_ATTENDANCE and att.name in with_checkins):
            safe_process(att, settings, resolver)
        if index % 200 == 199:
            frappe.db.commit()  # nosemgrep - long maintenance loop
