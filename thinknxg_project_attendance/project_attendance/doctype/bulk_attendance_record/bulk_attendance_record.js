// thinkNXG Project Attendance - Bulk Attendance Record
frappe.provide("thinknxg_project_attendance");

thinknxg_project_attendance.MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
];
thinknxg_project_attendance.WORKED = ["Present", "Half Day", "Work From Home"];
thinknxg_project_attendance.normal_hours = 8;

frappe.ui.form.on("Bulk Attendance Record", {
    setup(frm) {
        frm.set_query("employee", () => {
            const filters = { status: "Active" };
            if (frm.doc.company) filters.company = frm.doc.company;
            if (frm.doc.grade) filters.grade = frm.doc.grade;
            return { filters };
        });
        const project_query = () => {
            const filters = { status: ["!=", "Cancelled"], is_active: "Yes" };
            if (frm.doc.company) filters.company = frm.doc.company;
            return { filters };
        };
        frm.set_query("common_project", project_query);
        frm.set_query("project", "details", project_query);

        frappe.db
            .get_single_value("Project Attendance Settings", "normal_working_hours")
            .then((value) => {
                if (flt(value) > 0) thinknxg_project_attendance.normal_hours = flt(value);
            });
    },

    onload(frm) {
        if (!frm.is_new()) return;
        const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
        if (!frm.doc.posting_month) {
            frm.doc.posting_month = thinknxg_project_attendance.MONTHS[today.getMonth()];
        }
        if (!frm.doc.posting_year) {
            frm.doc.posting_year = String(today.getFullYear());
        }
        if (!frm.doc.company) {
            frm.doc.company = frappe.defaults.get_user_default("Company");
        }
        if (!frm.doc.from_date || !frm.doc.to_date) {
            frm.events.set_period(frm);
        }
        frm.refresh_fields();
    },

    refresh(frm) {
        frm.events.toggle_project_column(frm);

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Generate Days"), () => frm.events.generate_days(frm)).addClass(
                "btn-primary"
            );
            frm.add_custom_button(__("Fill Present"), () => frm.events.fill_present(frm), __("Fill"));
            frm.add_custom_button(__("Fill Project"), () => frm.events.fill_project(frm), __("Fill"));
            frm.add_custom_button(__("Fill Overtime"), () => frm.events.fill_overtime(frm), __("Fill"));
            frm.add_custom_button(__("Clear Days"), () => frm.events.clear_days(frm), __("Fill"));
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(
                __("Attendance"),
                () => frappe.set_route("List", "Attendance", { nxg_bulk_attendance_record: frm.doc.name }),
                __("View")
            );
            frm.add_custom_button(
                __("Project Overtime"),
                () => frappe.set_route("List", "Project Overtime", { bulk_attendance_record: frm.doc.name }),
                __("View")
            );
            frm.add_custom_button(
                __("Project Cost"),
                () =>
                    frappe.set_route("query-report", "Project Salary Expense Report", {
                        company: frm.doc.company,
                        employee: frm.doc.employee,
                        from_date: frm.doc.from_date,
                        to_date: frappe.datetime.add_months(frm.doc.to_date, 1),
                    }),
                __("View")
            );
            if (frm.doc.additional_salary) {
                frm.add_custom_button(
                    __("Additional Salary"),
                    () => frappe.set_route("Form", "Additional Salary", frm.doc.additional_salary),
                    __("View")
                );
            }
        }
    },

    posting_month(frm) {
        frm.events.set_period(frm);
    },

    posting_year(frm) {
        frm.events.set_period(frm);
    },

    set_period(frm) {
        const month = thinknxg_project_attendance.MONTHS.indexOf(frm.doc.posting_month);
        const year = cint(frm.doc.posting_year);
        if (month < 0 || year < 2000 || year > 2100) return;
        const pad = (n) => String(n).padStart(2, "0");
        const last = new Date(year, month + 1, 0).getDate();
        frm.set_value("from_date", `${year}-${pad(month + 1)}-01`);
        frm.set_value("to_date", `${year}-${pad(month + 1)}-${pad(last)}`);
    },

    company(frm) {
        if (frm.doc.employee) frm.set_value("employee", null);
    },

    grade(frm) {
        if (frm.doc.employee && frm.doc.grade) {
            frappe.db.get_value("Employee", frm.doc.employee, "grade").then((r) => {
                if (r.message && r.message.grade !== frm.doc.grade) frm.set_value("employee", null);
            });
        }
    },

    employee(frm) {
        if ((frm.doc.details || []).length) {
            frm.clear_table("details");
            frm.refresh_field("details");
        }
    },

    common_project(frm) {
        if (!frm.doc.project_change_allowed) frm.events.apply_common_project(frm, true);
    },

    project_change_allowed(frm) {
        frm.events.toggle_project_column(frm);
        if (!frm.doc.project_change_allowed) frm.events.apply_common_project(frm, true);
    },

    toggle_project_column(frm) {
        const grid = frm.fields_dict.details && frm.fields_dict.details.grid;
        if (!grid) return;
        grid.update_docfield_property("project", "read_only", frm.doc.project_change_allowed ? 0 : 1);
        frm.set_df_property("common_project", "reqd", frm.doc.project_change_allowed ? 0 : 1);
        frm.refresh_field("details");
    },

    apply_common_project(frm, overwrite) {
        (frm.doc.details || []).forEach((row) => {
            if (overwrite || !row.project) row.project = frm.doc.common_project;
        });
        frm.refresh_field("details");
    },

    generate_days(frm) {
        if (!frm.doc.employee) {
            frappe.msgprint(__("Select an Employee first."));
            return;
        }
        if (!frm.doc.project_change_allowed && !frm.doc.common_project) {
            frappe.msgprint(__("Select the Common Project first."));
            return;
        }
        frm.call({ doc: frm.doc, method: "generate_days", freeze: true }).then(() => {
            frm.dirty();
            frm.refresh_fields();
            frm.events.toggle_project_column(frm);
        });
    },

    fill_present(frm) {
        const hours = thinknxg_project_attendance.normal_hours;
        (frm.doc.details || []).forEach((row) => {
            if (row.status === "Holiday" || row.leave_application) return;
            row.status = "Present";
            row.working_hours = hours;
            row.leave_type = null;
        });
        frm.dirty();
        frm.refresh_field("details");
    },

    fill_project(frm) {
        if (!frm.doc.project_change_allowed) {
            frappe.msgprint(__("Enable Project Change Allowed to use different projects on individual days."));
            return;
        }
        frappe.prompt(
            [
                {
                    fieldname: "project",
                    label: __("Project"),
                    fieldtype: "Link",
                    options: "Project",
                    reqd: 1,
                    get_query: () => ({ filters: { status: ["!=", "Cancelled"], company: frm.doc.company } }),
                },
                { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frm.doc.from_date, reqd: 1 },
                { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frm.doc.to_date, reqd: 1 },
            ],
            (values) => {
                (frm.doc.details || []).forEach((row) => {
                    if (row.day >= values.from_date && row.day <= values.to_date) row.project = values.project;
                });
                frm.dirty();
                frm.refresh_field("details");
            },
            __("Fill Project"),
            __("Apply")
        );
    },

    fill_overtime(frm) {
        frappe.prompt(
            [
                { fieldname: "overtime_hours", label: __("OT Hours per Day"), fieldtype: "Float", reqd: 1 },
                { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frm.doc.from_date, reqd: 1 },
                { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frm.doc.to_date, reqd: 1 },
            ],
            (values) => {
                (frm.doc.details || []).forEach((row) => {
                    if (
                        row.day >= values.from_date &&
                        row.day <= values.to_date &&
                        thinknxg_project_attendance.WORKED.includes(row.status)
                    ) {
                        row.overtime_hours = flt(values.overtime_hours);
                    }
                });
                frm.dirty();
                frm.refresh_field("details");
            },
            __("Fill Overtime"),
            __("Apply")
        );
    },

    clear_days(frm) {
        frappe.confirm(__("Remove all days from the table?"), () => {
            frm.clear_table("details");
            frm.dirty();
            frm.refresh_field("details");
        });
    },
});

frappe.ui.form.on("Bulk Attendance Detail", {
    details_add(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        row.project = frm.doc.common_project;
        row.working_hours = thinknxg_project_attendance.normal_hours;
        frm.refresh_field("details");
    },

    day(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.day) return;
        const parts = row.day.split("-").map((p) => cint(p));
        const date = new Date(parts[0], parts[1] - 1, parts[2]);
        frappe.model.set_value(cdt, cdn, "weekday", date.toLocaleDateString("en-US", { weekday: "long" }));
    },

    status(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const hours = thinknxg_project_attendance.normal_hours;
        if (thinknxg_project_attendance.WORKED.includes(row.status)) {
            frappe.model.set_value(cdt, cdn, "working_hours", row.status === "Half Day" ? hours / 2 : hours);
        } else {
            frappe.model.set_value(cdt, cdn, "working_hours", 0);
            frappe.model.set_value(cdt, cdn, "overtime_hours", 0);
        }
    },
});
