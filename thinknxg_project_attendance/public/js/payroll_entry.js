// thinkNXG Project Attendance - Payroll Entry extension
frappe.ui.form.on("Payroll Entry", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;

        frm.add_custom_button(
            __("Project Salary Expense"),
            () => frappe.set_route("List", "Project Salary Expense", { payroll_entry: frm.doc.name }),
            __("Project Attendance")
        );

        if (!frm.doc.salary_slips_submitted) return;

        frm.add_custom_button(
            __("Post Project Salary Journal"),
            () => {
                frappe.call({
                    method: "thinknxg_project_attendance.utils.journal.post_project_salary_journal",
                    args: { payroll_entry: frm.doc.name },
                    freeze: true,
                    callback(r) {
                        if (r.message) {
                            frappe.msgprint(
                                __("Journal Entry {0} created.", [
                                    frappe.utils.get_form_link("Journal Entry", r.message, true),
                                ])
                            );
                        } else if (!r.exc) {
                            frappe.msgprint(__("Nothing to post. All project salary expenses are already posted."));
                        }
                    },
                });
            },
            __("Project Attendance")
        );
    },
});
