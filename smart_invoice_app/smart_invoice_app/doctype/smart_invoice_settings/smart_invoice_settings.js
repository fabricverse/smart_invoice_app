// Copyright (c) 2024, Bantoo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Smart Invoice Settings", {
	refresh(frm) {
        // add button to test connection
        if (frm.doc.environment == "Sandbox"){
            frm.add_custom_button(__("Test Connection"), function() {
                frappe.call({
                    method: "smart_invoice_app.app.test_connection"
                })
            });

            frm.add_custom_button(__("Sync"), function() {
                frappe.call({
                    method: "smart_invoice_app.app.sync_dependancies"
                })
            });
        }
	},

});
