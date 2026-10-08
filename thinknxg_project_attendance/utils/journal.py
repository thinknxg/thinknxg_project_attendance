"""Re-classification Journal Entry: moves payroll salary expense onto the Project dimension.

The Payroll Entry books salary expense per salary component account and payroll cost center.
This journal credits those same accounts (payroll cost center, payroll project if any) and debits
them again with the Project actually worked on, so the General Ledger and the project-wise
Profit and Loss carry the labour cost without touching the payroll journal itself.
"""
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form

from thinknxg_project_attendance.utils.allocation import PSE, get_component_account
from thinknxg_project_attendance.utils.common import currency_precision, get_settings


@frappe.whitelist()
def post_project_salary_journal(payroll_entry):
    """Manual trigger from the Payroll Entry form."""
    frappe.has_permission("Payroll Entry", "write", doc=payroll_entry, throw=True)
    if not cint(get_settings().post_reclass_journal):
        frappe.throw(
            _("Enable 'Post Project Journal Entry after Payroll' in {0} first.").format(
                get_link_to_form("Project Attendance Settings", "Project Attendance Settings")
            )
        )
    return make_reclass_journal(payroll_entry)


def post_in_background(payroll_entry):
    try:
        make_reclass_journal(payroll_entry)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title=f"Project salary journal failed for {payroll_entry}", message=frappe.get_traceback()
        )


def post_pending_project_journals():
    """Daily safety net for payroll entries whose project journal is still pending."""
    if not cint(get_settings().post_reclass_journal):
        return
    pending = frappe.get_all(
        PSE,
        filters={"gl_status": "Not Posted", "payroll_entry": ["is", "set"]},
        pluck="payroll_entry",
        distinct=True,
    )
    for payroll_entry in set(pending):
        if not cint(frappe.db.get_value("Payroll Entry", payroll_entry, "salary_slips_submitted")):
            continue
        post_in_background(payroll_entry)
        frappe.db.commit()  # nosemgrep - each payroll entry is an independent unit of work


def make_reclass_journal(payroll_entry):
    settings = get_settings()
    if not cint(settings.post_reclass_journal):
        return None

    payroll = frappe.db.get_value(
        "Payroll Entry",
        payroll_entry,
        ["name", "company", "posting_date", "project", "docstatus", "start_date", "end_date"],
        as_dict=True,
    )
    if not payroll or payroll.docstatus != 1:
        return None

    expenses = frappe.get_all(
        PSE,
        filters={"payroll_entry": payroll_entry, "gl_status": "Not Posted"},
        fields=["name", "project", "cost_center", "source_cost_center"],
    )
    if not expenses:
        return None

    precision = currency_precision()
    expense_map = {e.name: e for e in expenses}
    rows = frappe.get_all(
        "Project Salary Allocation",
        filters={"parent": ["in", list(expense_map)], "parenttype": PSE},
        fields=["name", "parent", "salary_component", "expense_account", "amount"],
    )

    entries = defaultdict(float)  # (account, project, cost_center) -> signed amount (+ debit / - credit)
    account_cache = {}
    missing = set()
    for row in rows:
        account = row.expense_account
        if not account:
            account = get_component_account(row.salary_component, payroll.company, settings, account_cache)
            if account:
                frappe.db.set_value(
                    "Project Salary Allocation", row.name, "expense_account", account, update_modified=False
                )
        if not account:
            missing.add(row.salary_component)
            continue

        expense = expense_map[row.parent]
        amount = flt(row.amount, precision)
        entries[(account, expense.project, expense.cost_center)] += amount
        entries[(account, payroll.project or "", expense.source_cost_center)] -= amount

    if missing:
        frappe.throw(
            _("Set the expense account for company {0} in Salary Component(s): {1}").format(
                payroll.company, ", ".join(sorted(missing))
            ),
            title=_("Salary Component Account Missing"),
        )

    accounts = []
    for (account, project, cost_center), amount in entries.items():
        amount = flt(amount, precision)
        if not amount:
            continue
        line = {"account": account, "cost_center": cost_center}
        if project:
            line["project"] = project
        if amount > 0:
            line["debit_in_account_currency"] = amount
        else:
            line["credit_in_account_currency"] = abs(amount)
        accounts.append(line)

    names = list(expense_map)
    if not accounts:
        frappe.db.set_value(PSE, {"name": ["in", names]}, "gl_status", "Not Required")
        return None

    journal = frappe.new_doc("Journal Entry")
    journal.update(
        {
            "voucher_type": "Journal Entry",
            "company": payroll.company,
            "posting_date": payroll.posting_date,
            "user_remark": _("Project salary allocation for Payroll Entry {0} ({1} to {2})").format(
                payroll.name, payroll.start_date, payroll.end_date
            ),
            "nxg_project_salary_reclass": 1,
            "nxg_payroll_entry": payroll.name,
        }
    )
    for line in accounts:
        journal.append("accounts", line)
    journal.flags.ignore_permissions = True
    journal.insert()
    if cint(settings.auto_submit_journal):
        journal.submit()

    frappe.db.set_value(
        PSE, {"name": ["in", names]}, {"journal_entry": journal.name, "gl_status": "Posted"}
    )
    return journal.name


def reset_expenses_for_journal(journal_entry):
    frappe.db.set_value(
        PSE, {"journal_entry": journal_entry}, {"journal_entry": None, "gl_status": "Not Posted"}
    )


def reverse_journal(journal_entry):
    """Detach and cancel (or delete, if still draft) a project salary journal."""
    reset_expenses_for_journal(journal_entry)
    docstatus = frappe.db.get_value("Journal Entry", journal_entry, "docstatus")
    if docstatus == 1:
        journal = frappe.get_doc("Journal Entry", journal_entry)
        journal.flags.ignore_permissions = True
        journal.cancel()
    elif docstatus == 0:
        frappe.delete_doc("Journal Entry", journal_entry, ignore_permissions=True, force=True)
