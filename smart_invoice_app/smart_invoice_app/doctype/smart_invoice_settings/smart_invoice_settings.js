// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Smart Invoice Settings", {
    refresh(frm) {
        if (frm.is_new()) {
            frm.set_value("company", "");
        }
        add_buttons(frm);
        onboarding(frm);

        frm.set_query("default_item_tax", function () {
            return {
                filters: {
                    company: frm.doc.company,
                },
            };
        });
    },

    after_save(frm) {
        // Explicitly re-render the intro layout right after a successful save payload arrives
        onboarding(frm);
    },

    base_url: function (frm) {
        save_if_saved(frm);
    },

    tpin: function (frm) {
        let vsdc = frm.doc.tpin ? String(frm.doc.tpin) + "_VSDC" : "";
        frm.set_value("vsdc_serial", vsdc);
    },

    environment: function (frm) {
        set_environment(frm);
    },

    use_custom_server: function (frm) {
        set_environment(frm);
    },
});

function save_if_saved(frm) {
    if (!frm.doc.__islocal) {
        frm.save();
    }
}

function onboarding(frm) {
    // Check both standard __onload context and action server response dictionary
    const onboarding_data =
        (frm.doc.__onload && frm.doc.__onload.onboarding) ||
        (frm.sidebar_data && frm.sidebar_data.onboarding);

    if (onboarding_data) {
        // 1. Set the dynamic header intro message
        if (onboarding_data.intro_message) {
            // Clear any existing stale intro containers before appending the active step instruction
            frm.set_intro("");
            frm.set_intro(
                onboarding_data.intro_message,
                onboarding_data.intro_color || "blue",
            );
        } else {
            frm.set_intro("");
        }

        // 2. Clear and set the dashboard status indicator color explicitly
        if (frm.doc.status) {
            frm.page.set_indicator(
                frm.doc.status,
                onboarding_data.indicator_color || "gray",
            );
        }
    }
}

function set_environment(frm) {
    if (!frm.doc.environment || frm.doc.use_custom_server == 1) return;

    frappe.call({
        method: "get_environments",
        doc: frm.doc,
        callback: function (r) {
            frm.set_value("base_url", r.message[frm.doc.environment]);
            save_if_saved(frm);
        },
    });
}

function add_buttons(frm) {
    if (!frm.doc.__islocal) {
        frm.add_custom_button(
            __("Connection Test"),
            function () {
                frappe.call({
                    method: "smart_invoice_api.api.test_connection",
                    args: { company_name: frm.doc.name },
                });
            },
            "Menu",
        );

        frm.add_custom_button(
            __("Load Parameters"),
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
                    args: { company_name: frm.doc.company },
                    callback: function () {
                        frm.reload_doc();
                    },
                });
            },
            "Menu",
        );

        if (frm.doc.loaded_initialization_data == 1) {
            frm.add_custom_button(
                __("Re-initialize Device"),
                function () {
                    frappe.call({
                        method: "initialize_virtual_device",
                        doc: frm.doc,
                    });
                },
                "Menu",
            );
        }

        frm.page
            .get_inner_group_button("Menu")
            .find("button")
            .removeClass("btn-default")
            .addClass("btn-success");
    }
}
