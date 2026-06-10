// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Smart Invoice Settings", {
	refresh(frm) {
        initialize_doc(frm);
        // add button to test connection
        if (!frm.doc.__islocal){
            frm.add_custom_button(__("Connection Test"), function() {
                frappe.call({
                    method: "smart_invoice_api.api.test_connection"
                })
            }, "Menu");

            // frm.add_custom_button(__("Update ZRA Data"), function() {
            //     frappe.call({
            //         method: "smart_invoice_app.app.sync_dependancies"
            //     })
            // }, "Menu");

            frm.add_custom_button(__("Get ZRA Codes"), function() {
                frappe.call({
                    method: "smart_invoice_app.app.initialize"
                })
            }, "Menu");

            frm.add_custom_button(__("Initialize Virtual Device"), function() {
                frappe.call({
                    method: "initialize_virtual_device",
                    doc: frm.doc,
                    callback: (r) => { }
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


function initialize_doc(frm){
    if (frm.doc.base_url) return;

    frappe.call({
        method: "initialize_doc",
        doc: frm.doc,
        callback: (r) => { }
    });
}