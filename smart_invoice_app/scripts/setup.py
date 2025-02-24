import frappe
from smart_invoice_app.scripts.branch import check_branches_setup, get_branch_code_by_name

@frappe.whitelist()
def check_setup():
    branches_setup = check_branches_setup()

    fully_setup = branches_setup == True
    return {
        'system_is_setup': fully_setup, 
        'branches_setup': branches_setup
    }

@frappe.whitelist()
def set_branch(branch):
    frappe.session.branch = branch
    frappe.session.branch_code = get_branch_code_by_name(branch)

    print(f"Branch set to {frappe.session.data.branch} with code {frappe.session.data.branch_code}")
    return

    # change to using cache
    # https://discuss.frappe.io/t/add-data-to-a-user-session/5254/2?u=adam26d
    # use 