frappe.listview_settings['ASYCUDA Verification'] = {
    refresh: function(listview) {
        // download_imports(listview);

        listview.page.add_inner_button(__("Download Imports"), function() {
            download_imports(listview);
             
        });
        listview.page.inner_toolbar.find('button:contains("Download Imports")').removeClass('btn-default').addClass('btn-primary');
    },
};

function download_imports(listview){
    frappe.call({
        method: "smart_invoice_app.smart_invoice_app.doctype.asycuda_verification.asycuda_verification.get",
        args: {
            from_list: true
        },
        callback: (r) => {
            listview.refresh();
        }
    });
}