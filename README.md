# thinkNXG Project Attendance

Project based bulk employee attendance, overtime and project salary costing for
**Frappe / ERPNext / Frappe HR v16**.

The app is an input and costing layer on top of the standard doctypes. It does not replace or
patch Attendance, Additional Salary, Salary Slip, Payroll Entry or Journal Entry.

```
Bulk Attendance Record ──submit──► Attendance (one per day, with Project + OT hours)
                        ├────────► Project Overtime (one per OT day: hours x rate, per project)
                        └────────► Additional Salary (total OT, picked up by the payroll run)

Payroll Entry ──► Salary Slip ──submit──► Project Salary Expense (one per slip x project)
              └─► accrual Journal Entry ─► Project re-classification Journal Entry (GL / P&L by Project)
```

## What is new in 1.3

- **Fix: "Page project-salary-expense not found".** Project Salary Expense and Project Attendance
  Ledger were flagged *User Cannot Search*, which removes a DocType's list page for users who
  only have read access. The flag is gone; both lists open normally after `bench migrate`.
- **Common Shift / Shift Change Allowed** on the Bulk Attendance Record, working like the project
  pair: the Common Shift (default: the employee's Default Shift) applies to every day and the row
  Shift is read-only unless Shift Change Allowed is ticked. The same two fields are in the
  *Create for Multiple Employees* dialog; an empty Common Shift there means each employee's own
  Default Shift.
- **Days are generated automatically** on a new Bulk Attendance Record as soon as the month,
  the employee and the project are known, and again when the month or year is changed. Selecting
  the employee also proposes the Common Shift and, from the Employee Project Assignment or the
  default project, the Common Project. The Generate Days button remains for a manual refresh.
- **Employee Project Assignment with several projects.** One assignment now holds a table of
  projects with Allocation % (total must be 100) and one primary project. Hours of checkins
  without a project are shared between the projects by percentage. Only one active assignment
  per employee and date is allowed. Existing assignments are converted on migrate.

Upgrade: `bench --site yoursite migrate`, `bench build --app thinknxg_project_attendance`,
`bench --site yoursite clear-cache`.

## What is new in 1.2: overtime approval

Overtime calculated from checkins is no longer paid automatically.

- Every checkin **Project Overtime** starts with Approval Status **Pending**.
- An approver opens the record (or selects many in the list) and chooses **Approve**,
  **Reject**, **Change Approved Hours** or **Reset to Pending**. Approved hours can be less than
  the recorded hours; only approved hours x rate are paid and costed to the project.
- Approvers: HR Manager, System Manager and the optional *Additional Overtime Approver Role* in
  the settings.
- Only **Approved** overtime is posted as Additional Salary. Submitting a Payroll Entry posts all
  approved, unposted overtime up to the period end, so overtime approved late is paid with the
  next payroll.
- Pending overtime produces a warning on the Payroll Entry, or blocks it when *Block Payroll Entry
  while Overtime is Pending* is ticked.
- Changing an approval after the overtime was posted but before it is in a salary slip takes the
  Additional Salary back automatically; once it is in a slip the slip must be cancelled first.
- Overtime typed on a Bulk Attendance Record is approved by submitting that record.
- Approvals survive a ledger rebuild as long as the overtime hours of that project and day are
  unchanged. Every decision is written to the record's timeline.
- Untick *Require Approval for Checkin Overtime* to return to automatic payment.

Upgrade: `bench --site yoursite migrate`. Overtime already posted to payroll is marked Approved;
checkin overtime not yet posted becomes Pending.

## What is new in 1.1: Employee Checkin / Auto Attendance

Attendance now reaches project costing from two sources through one layer, the
**Project Attendance Ledger**:

```
Employee Checkin (with Project) ─► HRMS Auto Attendance ─► Attendance ─┐
Bulk Attendance Record ───────────────────────────────────────────────┤
                                                                       ▼
                                                     Project Attendance Ledger
                                                       │                 │
                                             salary allocation     Project Overtime
                                                       └────────┬────────┘
                                          Salary Slip ─► Project Salary Expense ─► GL / P&L
```

- HRMS Auto Attendance is untouched. When it submits an Attendance, the app reads the checkins of
  that shift day, splits them into intervals, resolves a project per interval and writes ledger rows.
- One employee can work on several projects on the same day; every checkin with a project starts
  a new project interval.
- Hours beyond the standard hours become **Project Overtime**, attributed chronologically (or
  proportionally) to the projects of the day.
- Before a **Payroll Entry** is submitted, approved and unposted checkin overtime of its employees
  is posted as one **Additional Salary** per employee (see 1.2 for the approval step).
- Salary allocation, overtime, Project Salary Expense and all reports read the ledger only.

### Project resolution (first match wins)

1. Project on the Employee Checkin (typed, sent by API, or stamped from **Project Device Mapping**
   by Device ID).
2. **Employee Project Assignment** active on the date. Its projects share the hours by
   Allocation %. An assignment with *Allow Checkin Override* off wins over step 1 unless
   the checkin is marked *Is Project Override*.
3. Default Project on the Employee.
4. Default Project on the Department.
5. *Project for Unallocated Hours* in the settings.
6. **Unallocated**: the ledger row has no project. Its salary share is shown as an Unallocated
   Project Salary Expense and stays on the payroll cost center, so no cost disappears.

A log without a project inherits the project of the previous log of the day.

### One costing source per day

A day is costed from the Bulk Attendance Record **or** from checkin attendance, never both.
A Bulk Attendance Record cannot be submitted for days that already have Attendance, and an
Attendance arriving for a day covered by a Bulk Attendance Record is not written to the ledger
(an Error Log entry records it). Ledger rows are stamped with the Salary Slip that costed them;
stamped days cannot be reprocessed or cancelled until the slip is cancelled.

### Setup for checkins

1. Shift Type with **Enable Auto Attendance**; leave its **Overtime Type** empty (the native HRMS
   overtime slip and this app must not both pay overtime).
2. Project Attendance Settings > Employee Checkin / Auto Attendance: standard hours source
   (settings or shift duration), overtime allocation, minimum overtime minutes, holiday rule,
   project for unallocated hours.
3. Project Device Mapping for site devices; Employee Project Assignment and default projects
   for everyone else.
4. Mobile / kiosk integrations can call
   `thinknxg_project_attendance.api.project_checkin(log_type, project, device_id, latitude, longitude)`.

### Tools

- **Project Attendance Ledger > Rebuild from Attendance**: reprocess a period after fixing
  projects, assignments or settings (costed days are kept).
- **Project Overtime > Post Unpaid Overtime**: post approved checkin overtime to payroll by hand (for slips
  made without a Payroll Entry, or after fixing a failure).
- Changing the project on a checkin that is already linked to Attendance rebuilds that day.
- A daily job processes attendance that has no ledger rows yet.
- Report **Project Attendance Hours**: days, regular and overtime hours per project, employee and
  source, available before payroll; filters for unallocated and not-yet-costed hours.

### Upgrade from 1.0

```bash
bench --site yoursite migrate
bench build --app thinknxg_project_attendance
```

The migration writes ledger rows for Bulk Attendance Records submitted with 1.0 and stamps
periods that are already costed.

## Installation

```bash
cd ~/frappe-bench
bench get-app /path/to/thinknxg_project_attendance      # or the git URL
bench --site yoursite install-app thinknxg_project_attendance
bench --site yoursite migrate
bench build --app thinknxg_project_attendance
bench restart
```

Requires `erpnext` and `hrms` (v16) on the site.

On install the app creates its custom fields, default settings and an `Overtime` earning
salary component (if none exists).

## Setup checklist

1. **Project Attendance Settings**
   - Overtime method, normal hours/day, divisor days, multipliers, max OT hours/day.
   - Payroll Component for Overtime (default `Overtime`).
   - Salary allocation method: Working Days / Working Hours / Attendance Days.
   - Project journal posting on/off, auto submit, fallback expense account.
2. **Salary Component → Accounts**: set the expense account per company for every earning
   component including `Overtime` (HRMS needs this for the payroll journal anyway).
3. **Salary Structure Assignment** for every employee (needed for Additional Salary and for the
   `Basic / Working Hours x Multiplier` overtime method, which uses the assignment's *Base*).
4. For the `Hourly Rate x OT Hours` method fill **Overtime Hourly Rate** on Employee
   (fallback: Employee Grade).
5. Holiday List assigned to employees / company (holidays and weekly offs are pre-filled).

## Daily use

1. **Bulk Attendance Record → New**: month, year, grade (optional filter), employee, common project.
2. **Generate Days** fills one row per day: holidays from the holiday list, approved leave from
   Leave Applications, everything else Present.
3. Adjust status, project (if *Project Change Allowed*), shift, OT hours. Use the **Fill** menu
   for Present / Project (date range) / Overtime (date range).
4. **Save** validates, shows the OT rate and amount per row. **Submit** creates the documents.
5. From the list view, **Create for Multiple Employees** creates drafts for a whole grade /
   department in one go.

### Safeguards

| Check | Where |
|---|---|
| Overlapping Bulk Attendance Record for the employee | save |
| Dates outside the posting month / period, duplicate dates | save |
| Inactive employee, wrong company or grade, before joining / after relieving | save |
| Cancelled or inactive project, project of another company | save |
| Future dates (unless allowed in settings) | save |
| Status conflicts with an approved Leave Application; On Leave without leave type / application | save |
| OT on non-worked days, OT above the daily maximum, hours above 24 | save |
| Attendance already marked for any of the days | submit |
| Salary Slip already submitted for the period | submit / cancel |
| OT rate missing, OT component missing or not an Earning | submit |
| OT already paid in a Salary Slip | cancel |

Cancelling a Bulk Attendance Record cancels its Project Overtime, Additional Salary and Attendance.

## Overtime

| Method | Rate per OT hour |
|---|---|
| Basic / Working Hours x Multiplier | SSA Base / divisor days / normal hours x multiplier (holiday multiplier on holidays) |
| Hourly Rate x OT Hours | Employee (or Grade) Overtime Hourly Rate |
| Fixed OT Rate | Fixed rate from settings |

One **Additional Salary** per Bulk Attendance Record is created with payroll date = *To Date*,
so the salary slip of that period shows it as the Overtime earning. HRMS v16 also has its own
Overtime Slip feature; this app does not set an Overtime Type on Attendance, so the two do not
double-pay.

## Project Salary Expense and GL

On **Salary Slip submit** every earning that reaches the books is split:

- regular earnings by the allocation method, using the Project Attendance Ledger of the period;
- overtime directly to the project it was worked on (Project Overtime).

One **Project Salary Expense** per slip and project stores days, hours, salary, overtime, other
earnings and the component / account breakdown.

After the Payroll Entry submits its accrual journal, the app posts one **re-classification
Journal Entry** per Payroll Entry: it credits the salary expense accounts on the payroll cost
center and debits the same accounts with the **Project** (and the project's cost center, if set).
The standard *Profit and Loss Statement*, *General Ledger* and project profitability reports
filtered by Project then include labour cost. The journal can also be posted from
**Payroll Entry → Project Attendance → Post Project Salary Journal**; a daily job retries
anything pending.

Cancelling a Salary Slip removes its Project Salary Expenses, cancels the related project journal
and marks the overtime as unpaid again. Remaining slips of the same Payroll Entry are re-posted by
the button or the daily job.

## Reports

- **Project Salary Expense Report** – project x employee: days, salary, OT hours, OT amount,
  other earnings, total. Filters: company, dates, project, employee, department, grade,
  cost center, payroll entry.
- **Project Labour Cost Summary** – one line per project.

## Known limits

- Approval is a single step by one approver; there is no multi-level workflow or email notification.
- With the shift option *First Check-in and Last Check-out*, break time between an OUT and the
  next IN is counted (as HRMS does) and goes to the project that was just left.
- HRMS updates an existing half-day Attendance from checkins without events; the daily job (or
  Rebuild from Attendance) refreshes its ledger rows.

- One Bulk Attendance Record covers one employee and one calendar month (or part of it).
- If the salary is split over several payroll cost centers on the Salary Structure Assignment,
  the re-classification credits the employee's default payroll cost center only.
- Employer contributions are not allocated to projects.
- Salary Slips created outside a Payroll Entry get Project Salary Expenses for reporting, but no
  journal (HRMS posts no accrual for them either).
- Days without a project (or statuses Absent / On Leave) carry no allocation basis; paid leave
  cost is spread over the projects worked in the period.

## Uninstall

```bash
bench --site yoursite uninstall-app thinknxg_project_attendance
```

Custom fields added by the app are removed.

Before publishing, change `app_email` in `hooks.py` and the author in `pyproject.toml`.
