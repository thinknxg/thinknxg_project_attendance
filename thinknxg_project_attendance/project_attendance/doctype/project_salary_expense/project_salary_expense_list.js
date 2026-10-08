frappe.listview_settings["Project Salary Expense"] = {
    add_fields: ["gl_status"],
    get_indicator(doc) {
        const colors = { "Not Posted": "orange", Posted: "green", "Not Required": "grey" };
        return [__(doc.gl_status), colors[doc.gl_status] || "grey", "gl_status,=," + doc.gl_status];
    },
};
