frappe.query_reports["Project Salary Expense Report"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
        },
        { fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
        { fieldname: "grade", label: __("Grade"), fieldtype: "Link", options: "Employee Grade" },
        {
            fieldname: "source",
            label: __("Attendance Source"),
            fieldtype: "Select",
            options: ["", "Employee Checkin", "Bulk Attendance", "Attendance"],
        },
        { fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" },
        { fieldname: "payroll_entry", label: __("Payroll Entry"), fieldtype: "Link", options: "Payroll Entry" },
    ],
};
