frappe.listview_settings["Project Overtime"] = {
    add_fields: ["status"],
    get_indicator(doc) {
        const colors = { Unpaid: "orange", Paid: "green", Cancelled: "grey" };
        return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
    },
};
