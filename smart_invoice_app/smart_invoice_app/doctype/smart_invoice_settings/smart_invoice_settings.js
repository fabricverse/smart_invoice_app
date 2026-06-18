// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Smart Invoice Settings", {
    refresh(frm) {
        // initialize_doc(frm);
        onboarding(frm);

        // add button to test connection
        if (!frm.doc.__islocal) {
            frm.add_custom_button(
                __("Connection Test"),
                function () {
                    frappe.call({
                        method: "smart_invoice_api.api.test_connection",
                        args: {
                            company_name: frm.doc.name,
                        },
                    });
                },
                "Menu",
            );

            // frm.add_custom_button(__("Update ZRA Data"), function() {
            //     frappe.call({
            //         method: "smart_invoice_app.app.sync_dependancies"
            //     })
            // }, "Menu");

            // frm.add_custom_button(
            //     __("1. Initialize Virtual Device"),
            //     function () {
            //         frappe.call({
            //             method: "initialize_virtual_device",
            //             doc: frm.doc,
            //             callback: (r) => {},
            //         });
            //     },
            //     "Menu",
            // );

            frm.add_custom_button(
                __("Load Initialization Data"),
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
                        args: {
                            company: frm.doc.company,
                        },
                    });
                },
                "Menu",
            );

            frm.page
                .get_inner_group_button("Menu")
                .find("button")
                .removeClass("btn-default")
                .addClass("btn-success");
        }
    },
    onload: function (frm) {
        const tour_name = "Smart Invoice Onboarding";
        // frm.tour.init({ tour_name }).then(() => frm.tour.start());
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

    const company_defaults_setup =
        doc.default_uom &&
        doc.default_packing_unit &&
        doc.default_item_class &&
        doc.default_item_tax;

    const step_one_done = doc.status && doc.tpin && doc.base_url;

    const initialized = doc.initialized == 1;

    const fully_initialized =
        step_one_done && initialized && doc.loaded_initialization_data == 1;

    const initialized_and_set_defaults =
        fully_initialized && company_defaults_setup;

    const completed = fully_initialized && doc.branches_setup;

    if (!doc.status || !doc.tpin) {
        frm.set_value("status", "Setup Company & TPIN");
        frm.set_intro("");
    } else if (doc.status && doc.tpin && !doc.base_url) {
        frm.set_value("status", "Setup Environment");
        frm.set_intro("");
    } else if (step_one_done && !initialized) {
        frm.set_value("status", "Save");
        frm.set_intro(
            "<a>Step 1 of 4:</a> Save to initialize Smart Invoice",
            "blue",
        );
    } else if (initialized && !fully_initialized) {
        frm.set_value("status", "Load Initialization Data");
        frm.set_intro(
            "<a>Step 2 of 4:</a> Go to <b>Menu > Load Initialization Data</b>",
            "blue",
        );
    } else if (fully_initialized && !company_defaults_setup) {
        frm.set_value("status", "Setup Company Defaults");
        frm.set_intro(
            "<b>Step 3 of 4:</b> Setup Company Defaults and save",
            "blue",
        );
    } else if (initialized_and_set_defaults && !completed) {
        frm.set_value("status", "Setup Branches");
        frm.set_intro(
            "<div style='display: flex; justify-content: space-between; align-items: center;'>" +
                "<div><b>Step 4 of 4:</b> Add users to your branches</div>" +
                `<div style='margin-right: 2%;'><a class='btn btn-success btn-sm success-action' target='_blank' href='/app/branch?custom_company=${frm.doc.company}'>Branch Setup</a></div>` +
                "</div >            ",
            "blue",
        );

        frappe.call({
            method: "auto_check_branches_have_users",
            doc: frm.doc,
            callback: (e) => {},
        });
    } else if (completed) {
        if (doc.status != "Active") frm.set_value("status", "Active");
        frm.set_intro(
            "Smart Invoice is fully setup. You can test the connection from <b>Menu > Connection Test</b>",
            "green",
        );
    } else {
        frm.set_value("status", "Misconfigured");
        frm.set_intro(
            "Something's wrong. Test the connection from <b>Menu > Connection Test</b>",
            "yellow",
        );
    }

    console.log(doc.status);

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
        "Load Initialization Data": "blue",
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
