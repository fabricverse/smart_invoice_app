// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.listview_settings["Smart Invoice Settings"] = {
    get_indicator: function (doc) {
        const colors = {
            "Setup Company & TPIN": "gray",
            "Setup Environment": "gray",
            "Initialize Virtual Device": "gray",
            "Load Initialization Data": "blue",
            "Setup Company Defaults": "blue",
            "Setup Branches": "blue",
            Active: "green",
            Misconfigured: "red",
        };

        let color = colors[doc.status] || "gray";
        return [__(doc.status), color, "status,=," + doc.status];
    },
};
