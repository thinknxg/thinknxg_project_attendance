frappe.ui.form.on("Employee Project Assignment", {
    setup(frm) {
        frm.set_query("employee", () => ({ filters: { status: "Active" } }));
        frm.set_query("project", "projects", () => {
            const filters = { status: ["!=", "Cancelled"], is_active: "Yes" };
            if (frm.doc.company) filters.company = frm.doc.company;
            return { filters };
        });
    },

    refresh(frm) {
        frm.events.show_total(frm);
    },

    show_total(frm) {
        const total = (frm.doc.projects || []).reduce((sum, row) => sum + flt(row.allocation_percent), 0);
        frm.doc.total_allocation = total;
        frm.refresh_field("total_allocation");
        const grid = frm.fields_dict.projects && frm.fields_dict.projects.grid;
        if (grid && grid.wrapper) {
            grid.wrapper.find(".nxg-total").remove();
            const color = Math.abs(total - 100) < 0.01 ? "green" : "orange";
            grid.wrapper.append(
                `<div class="nxg-total text-muted small" style="margin-top:6px"><span class="indicator ${color}">${__(
                    "Total allocation: {0}%",
                    [total]
                )}</span></div>`
            );
        }
    },
});

frappe.ui.form.on("Employee Project Allocation", {
    projects_add(frm, cdt, cdn) {
        // propose what is left to reach 100%
        const row = locals[cdt][cdn];
        const used = (frm.doc.projects || [])
            .filter((r) => r.name !== row.name)
            .reduce((sum, r) => sum + flt(r.allocation_percent), 0);
        frappe.model.set_value(cdt, cdn, "allocation_percent", Math.max(100 - used, 0));
        if ((frm.doc.projects || []).length === 1) frappe.model.set_value(cdt, cdn, "is_primary", 1);
    },
    projects_remove(frm) {
        frm.events.show_total(frm);
    },
    allocation_percent(frm) {
        frm.events.show_total(frm);
    },
    is_primary(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.is_primary) return;
        (frm.doc.projects || []).forEach((r) => {
            if (r.name !== row.name && r.is_primary) r.is_primary = 0;
        });
        frm.refresh_field("projects");
    },
});
