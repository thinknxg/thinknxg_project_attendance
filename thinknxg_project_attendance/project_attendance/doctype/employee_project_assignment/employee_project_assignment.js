frappe.ui.form.on("Employee Project Assignment", {
    setup(frm) {
        frm.set_query("employee", () => ({ filters: { status: "Active" } }));
        frm.set_query("project", () => {
            const filters = { status: ["!=", "Cancelled"], is_active: "Yes" };
            if (frm.doc.company) filters.company = frm.doc.company;
            return { filters };
        });
    },
});
