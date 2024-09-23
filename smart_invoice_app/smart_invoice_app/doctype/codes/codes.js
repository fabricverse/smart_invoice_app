// Copyright (c) 2024, Bantoo and Partners and contributors
// For license information, please see license.txt

frappe.ui.form.on("Codes", {
	refresh(frm) {

	},
    before_save: function(frm) {
        // dont allow users to create new code class, they'll be created by system only

        if (frm.is_new()) {
            frappe.throw(__('You are not allowed to create a <strong>new</strong> entry. They will be created by the system only.'));
        }
    }
});
