frappe.listview_settings["Project Attendance Ledger"] = {
    add_fields: ["source", "is_unallocated", "salary_slip"],
    get_indicator(doc) {
        if (doc.is_unallocated) return [__("Unallocated"), "red", "is_unallocated,=,1"];
        if (doc.salary_slip) return [__("Costed"), "green", "salary_slip,is,set"];
        return [__(doc.source), doc.source === "Bulk Attendance" ? "blue" : "orange", "source,=," + doc.source];
    },
    onload(listview) {
        if (!frappe.user.has_role(["HR Manager", "System Manager"])) return;

        listview.page.add_inner_button(__("Rebuild from Attendance"), () => {
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
                        default: frappe.datetime.get_today(),
                    },
                ],
                (values) => {
                    frappe.call({
                        method: "thinknxg_project_attendance.utils.ledger.rebuild_ledger",
                        args: values,
                        freeze: true,
                        freeze_message: __("Rebuilding the ledger..."),
                        callback(r) {
                            if (!r.message) return;
                            if (r.message.queued) {
                                frappe.msgprint(__("The rebuild runs in the background."));
                                return;
                            }
                            const m = r.message;
                            frappe.msgprint(
                                __("Processed: {0}, already costed: {1}, skipped: {2}, covered by Bulk Attendance: {3}, failed: {4}", [
                                    m.processed || 0,
                                    m.costed || 0,
                                    m.skipped || 0,
                                    m.duplicate || 0,
                                    m.failed || 0,
                                ])
                            );
                            listview.refresh();
                        },
                    });
                },
                __("Rebuild Ledger from Attendance"),
                __("Rebuild")
            );
        });
    },
};
