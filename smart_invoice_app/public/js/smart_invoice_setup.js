// frappe.provide("erpnext");

console.log('asd')
// Wait for the smart-invoice-setup page to be initialized
$(document).ready(function() {
	
frappe.call({
	method: "smart_invoice_app.scripts.setup.check_setup",
	callback: (r=>{
		let setup_progress = r.message;

		if (r.error || !setup_progress){ console.log(r.error);
			return;
		}

		console.log('system_is_setup', setup_progress);

		if (setup_progress.system_is_setup){
			if(setup_progress.branches_setup){
				branch_selector();
				return;
			}
			else {
				frappe.show_alert("Please setup branches first");
			}
		}		
	})
});

});

// function branch_selector(){
// 	// show a persistent frappe dialog branch selector
// 	// if only one branch, set it and return
// 	console.log(frappe.session.user, frappe.session.branch);
// 	let dialog = new frappe.ui.Dialog({
// 		title: __('Select Branch'),
// 		fields: [
// 			{
// 				fieldtype: 'Link',
// 				fieldname: 'branch',
// 				label: __('Branch'),
// 				options: 'Branch',
// 				reqd: 1
// 			}
// 		],
// 		primary_action: function() {
// 			let branch = dialog.get_value('branch');
// 			console.log('branch', branch, 'selected');
// 			if (branch) {
// 				frappe.call({
// 					method: "smart_invoice_app.scripts.setup.set_branch",
// 					args: {
// 						branch: branch
// 					},
// 					callback: function(r) {
// 						if (!r.error) {

// 							console.log(frappe.session.user, frappe.session.branch);
// 							frappe.show_alert(__('Branch set to ' + branch));
// 							dialog.hide();
// 						}
// 					}
// 				});
// 			}
// 		}
// 	});
// 	dialog.show();
// }

function branch_selector() {
    frappe.call({
        method: "smart_invoice_app.scripts.branch.get_branches_with_setup",
        callback: function(r) {
            if (r.error) {
                frappe.show_alert(__("Error fetching branches: ") + r.message);
                return;
            }

            let branches = r.message;
            if (branches.length === 0) {
                frappe.show_alert(__("No branches are set up."));
                return;
            // } 
			// else if (branches.length === 1) {
            //     // Automatically select the only branch
            //     let branch = branches[0].name;
            //     set_session_branch(branch);
            //     frappe.show_alert(__("Branch set to ") + branch);
            } else {
                // Show dialog for branch selection
                show_branch_selection_dialog(branches);
            }
        }
    });
}

function show_branch_selection_dialog(branches) {
    // Populate the dialog with the list of branches
    let branch_options = branches.map(branch => ({ label: branch.name, value: branch.name }));
    let dialog = new frappe.ui.Dialog({
        title: __('Select Branch'),
        fields: [
            {
                fieldtype: 'Select',
                fieldname: 'branch',
                label: __('Branch'),
                options: branch_options,
                reqd: 1
            }
        ],
        primary_action: function() {
            let branch = dialog.get_value('branch');
            if (branch) {
                set_session_branch(branch);
                frappe.show_alert(__("Branch set to ") + branch);
                dialog.hide();
            }
        }
    });
    dialog.show();
}

function set_session_branch(branch) {
	frappe.session.branch = branch;
    // frappe.call({
    //     method: "smart_invoice_app.scripts.setup.set_branch",
    //     args: { branch: branch },
    //     callback: function(r) {
    //         if (!r.error) {
    //             // Refresh the session to update the branch
    //             frappe.session.branch = branch;
    //             frappe.show_alert(__("Branch set to ") + branch);
    //         } else {
    //             frappe.show_alert(__("Error setting branch: ") + r.message);
    //         }
    //     }
    // });
}