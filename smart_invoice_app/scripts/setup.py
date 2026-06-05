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
from frappe import _

@frappe.whitelist()
def get_initial_session_status():
    user = frappe.session.user
    
    # 1. Gather all operational branches based on permissions
    if user == "Administrator":
        # Administrator bypass: access all active operational branches
        allowed_branches = frappe.get_all(
            "Branch", 
            filters={"custom_branch_status": ["is", "set"]}, 
            fields=["name", "custom_bhf_id", "custom_tpin"]
        )
        # For Admin, we don't force an auto_selected true state unless there is literally 1 branch in system
        for b in allowed_branches:
            b["is_default"] = 0
    else:
        # Standard User query filtering via the custom_branch_users child table
        allowed_branches = frappe.db.sql("""
            SELECT 
                b.name, 
                b.custom_bhf_id, 
                b.custom_tpin, 
                bu.is_default
            FROM `tabBranch` b
            JOIN `tabBranch User` bu ON bu.parent = b.name
            WHERE bu.user_id = %s 
              AND bu.parenttype = 'Branch'
              AND b.custom_branch_status IS NOT NULL
        """, (user,), as_dict=True)

    if allowed_branches:
        return {"branches_setup": False}

    # 2. Rule: If user only has one branch, select it by default instantly
    if len(allowed_branches) == 1:
        single_branch = allowed_branches[0]
        set_branch(single_branch.name, single_branch.custom_bhf_id, single_branch.custom_tpin)
        
        return {
            "branches_setup": True,
            "auto_selected": True,
            "branches": allowed_branches,
            "active_branch_name": single_branch.name,
            "active_branch_id": single_branch.custom_bhf_id,
            "active_tpin": single_branch.custom_tpin
        }

    # 3. Rule: Multi-branch sorting. Sort by is_default descending (1 comes before 0)
    # This hoists their default branch to index 0
    allowed_branches.sort(key=lambda x: x.get("is_default", 0), reverse=True)

    return {
        "branches_setup": True,
        "auto_selected": False,
        "branches": allowed_branches
    }

@frappe.whitelist()
def set_branch(branch_doc_name, branch_id, tpin):
    """Saves the chosen branch context explicitly using Frappe's native defaults engine."""
    frappe.defaults.set_user_default("custom_active_branch", branch_id)
    frappe.defaults.set_user_default("custom_active_branch_name", branch_doc_name)
    frappe.defaults.set_user_default("custom_tpin", tpin)
    frappe.db.commit()

    return {
        "branch_id": branch_id,
        "branch_display_name": branch_doc_name,
        "tpin": tpin
    }