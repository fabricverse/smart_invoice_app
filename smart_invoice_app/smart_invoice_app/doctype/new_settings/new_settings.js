// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Smart Invoice Settings", {
    refresh(frm) {
        // initialize_doc(frm);

        // add button to test connection
        if (!frm.doc.__islocal) {
            frm.add_custom_button(
                __("Connection Test"),
                function () {
                    frappe.call({
                        method: "smart_invoice_api.api.test_connection",
                    });
                },
                "Menu",
            );

            // frm.add_custom_button(__("Update ZRA Data"), function() {
            //     frappe.call({
            //         method: "smart_invoice_app.app.sync_dependancies"
            //     })
            // }, "Menu");

            frm.add_custom_button(
                __("1. Initialize Virtual Device"),
                function () {
                    frappe.call({
                        method: "initialize_virtual_device",
                        doc: frm.doc,
                        callback: (r) => {},
                    });
                },
                "Menu",
            );

            frm.add_custom_button(
                __("2. Load Initialization Data"),
                function () {
                    frappe.show_alert(
                        {
                            message: __("Loading in the background..."),
                            indicator: "blue",
                        },
                        3,
                    );
                    frappe.call({
                        method: "smart_invoice_app.app.initialize",
                    });
                },
                "Menu",
            );

            frm.page
                .get_inner_group_button("Menu")
                .find("button")
                .removeClass("btn-default")
                .addClass("btn-info");
        }
    },
    environment: function (frm) {
        set_environment(frm);
    },
    use_custom_server: function (frm) {
        set_environment(frm);
    },
    setup: function (frm) {
        onboarding(frm);
    },
    base_url: function (frm) {
        onboarding(frm);
    },
    tpin(frm) {
        if (frm.doc.tpin) {
            frm.set_value("vsdc_serial", String(frm.doc.tpin) + "_VSDC");
        } else {
            frm.set_value("vsdc_serial", "");
        }
        frm.refresh_field("vsdc_serial");
        onboarding(frm);
    },
});
function onboarding(frm) {
    const doc = frm.doc;
    if (!doc.status && !doc.tpin) {
        frm.set_value("status", "Setup Company & TPIN");
    } else if (doc.status == "Setup Company & TPIN" && !doc.base_url) {
        frm.set_value("status", "Setup Environment");
    } else if (doc.status == "Setup Environment" && doc.base_url) {
        frm.set_value("status", "Initialize Virtual Device");
    }
    // else if (doc.status == "Setup Environment" ) {
    //     frm.set_value("status", ")'
    frm.page.set_indicator(
        `${frm.doc.status}`,
        get_status_color(frm.doc.status),
    );
}

function get_status_color(status) {
    const colors = {
        "Setup Company & TPIN": "gray",
        "Setup Environment": "gray",
        "Initialize Virtual Device": "gray",
        "Load Initization Data": "blue",
        "Setup Company Defaults": "blue",
        "Setup Branches": "blue",
        Active: "green",
        Misconfigured: "red",
    };
    return colors[status] || "gray";
}

function set_environment(frm) {
    // set server base_url if use_custom_server == 0
    if (!frm.doc.environment || frm.doc.use_custom_server == 1) return;

    frappe.call({
        method: "get_environments",
        doc: frm.doc,
        callback: function (r) {
            urls = r.message;
            frm.set_value("base_url", urls[frm.doc.environment]);
        },
    });
}

function initialize_doc(frm) {
    if (frm.doc.base_url) return;

    frappe.call({
        method: "initialize_doc",
        doc: frm.doc,
        callback: (r) => {},
    });
}
