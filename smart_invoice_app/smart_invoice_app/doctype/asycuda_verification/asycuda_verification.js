// Copyright (c) 2024, Bantoo and Partners and contributors
// For license information, please see license.txt

frappe.ui.form.on("ASYCUDA Verification", {
	refresh(frm) {
        add_create_buttons(frm);
	},
});


function add_create_buttons(frm){

    frm.add_custom_button(__("Purchase Receipt"), function() {
        create_purchase_receipt(frm); 
    }, __("Create"));

    frm.add_custom_button(__("Purchase Invoice"), function() {
        create_purchase_invoice(frm);
    }, __("Create"));
    frm.page.set_inner_btn_group_as_primary(__("Create"));

    // frm.find('button:contains("Create")').removeClass('btn-default').addClass('btn-success');
    
}

function create_purchase_receipt(frm){
    // console.log("create_purchase_receipt");
    create_doc(frm, doc="purchase-receipt", method="create_purchase_receipt");    
}
function create_purchase_invoice(frm){
    // console.log("create_purchase_invoice");
    create_doc(frm, doc="purchase-invoice", method="create_purchase_invoice");
    
}
function create_doc(frm, doc, method){
    let d = new frappe.ui.Dialog({
        title: __('Select Supplier'),
        fields: [
            {
                label: __('Supplier'),
                fieldname: 'supplier',
                fieldtype: 'Link',
                options: 'Supplier',
                filters: { 'disabled': 0 },
                reqd: 1
            }
        ],
        size: 'small',
        primary_action_label: __('Create'),
        primary_action(values) {
            frappe.call({
                method: method,
                doc: frm.doc,
                args: {
                    supplier: values.supplier
                },
                callback: (r) => {
                    if(r && !r.error){
                        d.hide();
                        frappe.set_route(doc, r.message);
                        frm.reload_doc();
                    }
                }
            });
        }
    });

    d.show();
}