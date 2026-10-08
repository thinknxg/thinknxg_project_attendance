from thinknxg_project_attendance.utils.allocation import (
    create_project_salary_expenses,
    remove_project_salary_expenses,
)


def on_submit(doc, method=None):
    create_project_salary_expenses(doc)


def on_cancel(doc, method=None):
    remove_project_salary_expenses(doc)
