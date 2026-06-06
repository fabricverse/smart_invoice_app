frappe.listview_settings['ASYCUDA Verification'] = {
    refresh: function(listview) {
        // download_imports(listview);

        listview.page.add_inner_button(__("Download Imports"), function() {
            download_imports(listview);             
        }, __("Smart Invoice"));
        
        listview.page.get_inner_group_button("Smart Invoice")
        .find("button")
        .removeClass("btn-default")
        .addClass("btn-info");
    },
	onload: function(listview) {
        // Prevent layout shifting and wobbling when global progress overlays load
        document.documentElement.style.scrollbarGutter = "stable";
        
        // Listen for final logic to trigger alerts and reload the specific form
        frappe.realtime.on("sync_progress", function(data) {
            // 1. Scoping Guard: Ensure this event belongs to the active document on screen
            if (!data.name) {
                return; 
            }

            
        
            let indicator = data.indicator;
            let message = data.message || __("Sync failure without an explicit error message.");
            console.log(message); // Debug log to inspect incoming data structure
        
            if (indicator.toLowerCase() === "red") {
                frappe.warn(
                    __("Smart Invoice encountered the following error:"),
                    `${message}<br>`, // Message body
                    () => {
                        // Primary Action: Redirect to the sync log document if name exists
                        frappe.set_route("Form", "Sync Request", data.name);
                    },
                    __("Open"),
                );
            } else {
                frappe.show_alert({ message: message, indicator: indicator}, 2);
            }
        });
        
        // Listen for final logic execution to reload the document details
        frappe.realtime.on("reload_form", function(data) {
            // Optional verification to confirm context matches session modifier/document
            listview.refresh();
        });
    },
    unload: function(frm) {
        // Clean up listener when leaving the form to prevent memory leaks
        frappe.realtime.off('sync_progress');
        frappe.realtime.off('progress');
    }
};

function download_imports(listview){
    frappe.call({
        method: "smart_invoice_app.smart_invoice_app.doctype.asycuda_verification.asycuda_verification.get_import_items",
        args: {
            from_list: true
        },
        callback: (r) => {
            listview.refresh();
        }
    });
}