// thinkNXG Project Attendance - Project Overtime approval
frappe.provide("thinknxg_project_attendance");

thinknxg_project_attendance.overtime_approval = function (names, action, values, done) {
    frappe.call({
        method: "thinknxg_project_attendance.utils.approval.set_overtime_approval",
        args: {
            names: names,
            action: action,
            approved_hours: values && values.approved_hours,
            remarks: values && values.remarks,
        },
        freeze: true,
        callback(r) {
            if (r.message) {
                frappe.show_alert({
                    message: __("{0} record(s) updated, {1} skipped.", [r.message.changed, r.message.skipped]),
                    indicator: r.message.skipped ? "orange" : "green",
                });
            }
            done && done();
        },
    });
};

frappe.ui.form.on("Project Overtime", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1 || frm.doc.salary_slip || frm.doc.bulk_attendance_record) return;

        frappe
            .xcall("thinknxg_project_attendance.utils.approval.get_approval_context")
            .then((context) => {
                if (!context || !context.can_approve) return;
                const reload = () => frm.reload_doc();
                const status = frm.doc.approval_status;

                if (status !== "Approved") {
                    frm.add_custom_button(__("Approve"), () => {
                        frappe.prompt(
                            [
                                {
                                    fieldname: "approved_hours",
                                    label: __("Approved OT Hours"),
                                    fieldtype: "Float",
                                    reqd: 1,
                                    default: frm.doc.overtime_hours,
                                    description: __("Recorded: {0} hours. Enter less to approve only part of it.", [
                                        frm.doc.overtime_hours,
                                    ]),
                                },
                                { fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
                            ],
                            (values) =>
                                thinknxg_project_attendance.overtime_approval([frm.doc.name], "Approve", values, reload),
                            __("Approve Overtime"),
                            __("Approve")
                        );
                    }).addClass("btn-primary");
                }
                if (status !== "Rejected") {
                    frm.add_custom_button(__("Reject"), () => {
                        frappe.prompt(
                            [{ fieldname: "remarks", label: __("Reason"), fieldtype: "Small Text", reqd: 1 }],
                            (values) =>
                                thinknxg_project_attendance.overtime_approval([frm.doc.name], "Reject", values, reload),
                            __("Reject Overtime"),
                            __("Reject")
                        );
                    });
                }
                if (status === "Approved") {
                    frm.add_custom_button(__("Change Approved Hours"), () => {
                        frappe.prompt(
                            [
                                {
                                    fieldname: "approved_hours",
                                    label: __("Approved OT Hours"),
                                    fieldtype: "Float",
                                    reqd: 1,
                                    default: frm.doc.approved_hours,
                                },
                                { fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
                            ],
                            (values) =>
                                thinknxg_project_attendance.overtime_approval([frm.doc.name], "Approve", values, reload),
                            __("Change Approved Hours"),
                            __("Save")
                        );
                    });
                }
                if (status !== "Pending") {
                    frm.add_custom_button(__("Reset to Pending"), () =>
                        thinknxg_project_attendance.overtime_approval([frm.doc.name], "Reset", null, reload)
                    );
                }
            });

        if (frm.doc.approval_status === "Pending") {
            frm.dashboard.set_headline(__("This overtime is pending approval and will not be paid until it is approved."));
        }
    },
});
