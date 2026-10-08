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

- regular earnings by the allocation method, using the project recorded on each day's Attendance;
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
