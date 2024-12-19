// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Smart Invoice Settings", {
	refresh(frm) {
        // add button to test connection
        if (!frm.doc.__islocal){
            frm.add_custom_button(__("Connection Test"), function() {
                frappe.call({
                    method: "smart_invoice_app.app.test_connection"
                })
            }, "Menu");

            frm.add_custom_button(__("Update ZRA Data"), function() {
                frappe.call({
                    method: "smart_invoice_app.app.sync_dependancies"
                })
            }, "Menu");

            frm.add_custom_button(__("Initialize ZRA Data"), function() {
                frappe.call({
                    method: "smart_invoice_app.app.initialize"
                })
            }, "Menu");

            frm.add_custom_button(__("Initialize VSDC"), function() {
                frappe.call({
                    method: "initialize_vsdc",
                    doc: frm.doc,
                    callback: (r) => {
                        if (r.error){
                            frappe.msgprint({
                                title: __('Initialization Failure'),
                                indicator: 'yellow',
                                message: r.error
                            });
                        }
                        else {
                            frappe.msgprint({
                                title: __('Smart Invoice Initialization'),
                                indicator: 'green',
                                message: r.message
                            });
                        }
                    }
                })
            }, "Menu");

            frm.page.get_inner_group_button("Menu")
            .find("button")
            .removeClass("btn-default")
            .addClass("btn-info");
        }
	},
    tpin(frm){
        if (frm.doc.tpin){
            frm.set_value("vsdc_serial", String(frm.doc.tpin) + "_VSDC");
        }
        else{
            frm.set_value("vsdc_serial", "");
        }
        frm.refresh_field("vsdc_serial");
    }

});
