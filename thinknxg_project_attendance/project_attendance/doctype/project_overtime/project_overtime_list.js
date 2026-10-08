frappe.listview_settings["Project Overtime"] = {
    add_fields: ["status", "approval_status", "docstatus"],
    get_indicator(doc) {
        if (doc.docstatus === 2 || doc.status === "Cancelled") {
            return [__("Cancelled"), "grey", "status,=,Cancelled"];
        }
        if (doc.status === "Paid") return [__("Paid"), "green", "status,=,Paid"];
        if (doc.approval_status === "Pending") {
            return [__("Pending Approval"), "orange", "approval_status,=,Pending"];
        }
        if (doc.approval_status === "Rejected") return [__("Rejected"), "red", "approval_status,=,Rejected"];
        return [__("Approved, Unpaid"), "blue", "approval_status,=,Approved|status,=,Unpaid"];
    },
    onload(listview) {
        const act = (action, values) => {
            const names = listview.get_checked_items(true);
            if (!names.length) {
                frappe.msgprint(__("Select the overtime records first."));
                return;
            }
            const run = () => {
                frappe.call({
                    method: "thinknxg_project_attendance.utils.approval.set_overtime_approval",
                    args: { names: names, action: action, remarks: values && values.remarks },
                    freeze: true,
                    callback(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: __("{0} record(s) updated, {1} skipped.", [
                                    r.message.changed,
                                    r.message.skipped,
                                ]),
                                indicator: r.message.skipped ? "orange" : "green",
                            });
                        }
                        listview.clear_checked_items();
                        listview.refresh();
                    },
                });
            };
            run();
        };

        frappe.xcall("thinknxg_project_attendance.utils.approval.get_approval_context").then((context) => {
            if (!context || !context.can_approve) return;
            listview.page.add_actions_menu_item(__("Approve Overtime"), () => {
                frappe.confirm(__("Approve the full recorded hours of the selected records?"), () => act("Approve"));
            });
            listview.page.add_actions_menu_item(__("Reject Overtime"), () => {
                frappe.prompt(
                    [{ fieldname: "remarks", label: __("Reason"), fieldtype: "Small Text", reqd: 1 }],
                    (values) => act("Reject", values),
                    __("Reject Overtime"),
                    __("Reject")
                );
            });
            listview.page.add_inner_button(__("Pending Approval"), () => {
                listview.filter_area.add([["Project Overtime", "approval_status", "=", "Pending"]]);
            });
        });

        if (!frappe.user.has_role(["HR Manager", "HR User", "System Manager"])) return;

        listview.page.add_inner_button(__("Post Unpaid Overtime"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "company",
                        label: __("Company"),
                        fieldtype: "Link",
                        options: "Company",
                        default: frappe.defaults.get_user_default("Company"),
                    },
                    { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
                    {
                        fieldname: "from_date",
                        label: __("From Date"),
                        fieldtype: "Date",
                        reqd: 1,
                        default: frappe.datetime.month_start(),
                    },
                    {
                        fieldname: "to_date",
                        label: __("To Date"),
                        fieldtype: "Date",
                        reqd: 1,
                        default: frappe.datetime.month_end(),
                    },
                    {
                        fieldname: "payroll_date",
                        label: __("Payroll Date"),
                        fieldtype: "Date",
                        description: __("Date of the Additional Salary. Defaults to the To Date."),
                    },
                ],
                (values) => {
                    frappe.call({
                        method: "thinknxg_project_attendance.utils.overtime.post_unpaid_overtime",
                        args: values,
                        freeze: true,
                        callback(r) {
                            if (!r.message) return;
                            frappe.show_alert({
                                message: __("Additional Salary created for {0} employee(s), {1} failed.", [
                                    r.message.posted,
                                    r.message.failed,
                                ]),
                                indicator: r.message.failed ? "orange" : "green",
                            });
                            listview.refresh();
                        },
                    });
                },
                __("Post Approved Overtime to Payroll"),
                __("Post")
            );
        });
    },
};
