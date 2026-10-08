frappe.query_reports["Project Attendance Hours"] = {
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
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            reqd: 1,
        },
        { fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
        {
            fieldname: "source",
            label: __("Attendance Source"),
            fieldtype: "Select",
            options: ["", "Employee Checkin", "Bulk Attendance", "Attendance"],
        },
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: ["Period", "Day"],
            default: "Period",
        },
        { fieldname: "unallocated_only", label: __("Unallocated Only"), fieldtype: "Check" },
        { fieldname: "uncosted_only", label: __("Not Yet Costed in Payroll"), fieldtype: "Check" },
    ],
};
