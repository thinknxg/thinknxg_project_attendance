"""v1.2: overtime approval.

Existing overtime that is already on its way through payroll (Bulk Attendance, or posted to an
Additional Salary) is marked Approved. Checkin overtime not yet posted becomes Pending.
"""
import frappe


def execute():
    overtime = frappe.qb.DocType("Project Overtime")

    (
        frappe.qb.update(overtime)
        .set(overtime.approval_status, "Approved")
        .set(overtime.approved_hours, overtime.overtime_hours)
        .set(overtime.approval_remarks, "Approved before overtime approval was introduced")
        .where(overtime.docstatus == 1)
        .where(
            (overtime.bulk_attendance_record.isnotnull() & (overtime.bulk_attendance_record != ""))
            | (overtime.additional_salary.isnotnull() & (overtime.additional_salary != ""))
        )
    ).run()

    (
        frappe.qb.update(overtime)
        .set(overtime.approval_status, "Pending")
        .set(overtime.approved_hours, 0)
        .where(overtime.docstatus == 1)
        .where(overtime.bulk_attendance_record.isnull() | (overtime.bulk_attendance_record == ""))
        .where(overtime.additional_salary.isnull() | (overtime.additional_salary == ""))
    ).run()
