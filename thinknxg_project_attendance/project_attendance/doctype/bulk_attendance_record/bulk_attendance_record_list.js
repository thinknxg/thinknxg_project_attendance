frappe.listview_settings["Bulk Attendance Record"] = {
    add_fields: ["status", "docstatus"],
    get_indicator(doc) {
        const colors = {
            Draft: "red",
            Submitted: "blue",
            "Payroll Processed": "green",
            Cancelled: "grey",
        };
        return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
    },
    onload(listview) {
        if (!frappe.model.can_create("Bulk Attendance Record")) return;

        listview.page.add_inner_button(__("Create for Multiple Employees"), () => {
            const months = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            ];
            const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
            const dialog = new frappe.ui.Dialog({
                title: __("Create Bulk Attendance Records"),
                fields: [
                    {
                        fieldname: "company",
                        label: __("Company"),
                        fieldtype: "Link",
                        options: "Company",
                        reqd: 1,
                        default: frappe.defaults.get_user_default("Company"),
                    },
                    {
                        fieldname: "posting_month",
                        label: __("Posting Month"),
                        fieldtype: "Select",
                        options: months.join("\n"),
                        reqd: 1,
                        default: months[today.getMonth()],
                    },
                    {
                        fieldname: "posting_year",
                        label: __("Year"),
                        fieldtype: "Data",
                        reqd: 1,
                        default: String(today.getFullYear()),
                    },
                    { fieldtype: "Column Break" },
                    { fieldname: "grade", label: __("Grade"), fieldtype: "Link", options: "Employee Grade" },
                    { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
                    { fieldtype: "Section Break" },
                    { fieldname: "common_project", label: __("Common Project"), fieldtype: "Link", options: "Project" },
                    { fieldname: "project_change_allowed", label: __("Project Change Allowed"), fieldtype: "Check" },
                ],
                primary_action_label: __("Create Drafts"),
                primary_action(values) {
                    frappe.call({
                        method: "thinknxg_project_attendance.api.create_bulk_records",
                        args: values,
                        freeze: true,
                        freeze_message: __("Creating records..."),
                        callback(r) {
                            if (!r.message) return;
                            dialog.hide();
                            frappe.msgprint(
                                __("{0} draft record(s) created, {1} employee(s) skipped (already recorded or no days).", [
                                    r.message.created.length,
                                    r.message.skipped.length,
                                ])
                            );
                            listview.refresh();
                        },
                    });
                },
            });
            dialog.show();
        });
    },
};
