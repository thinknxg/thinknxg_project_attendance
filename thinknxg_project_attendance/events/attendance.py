"""Attendance -> Project Attendance Ledger.

Covers every Attendance that is not created by a Bulk Attendance Record: Auto Attendance from
Employee Checkins, manual Attendance, Attendance Requests, half-day leave ...
"""
from thinknxg_project_attendance.utils.ledger import release_attendance, safe_process


def on_submit(doc, method=None):
    if doc.get("nxg_bulk_attendance_record"):
        return
    # never raises: a costing problem must not make HRMS skip the attendance
    safe_process(doc)


def on_cancel(doc, method=None):
    # raises when the day is already costed in a Salary Slip
    release_attendance(doc.name)
