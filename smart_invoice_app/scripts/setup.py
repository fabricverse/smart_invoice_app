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
    hash_key = f"session_branch:{user}"
    
    # 1. Gather all operational branches first based on authorization permissions
    if user == "Administrator":
        allowed_branches = frappe.get_all(
            "Branch", 
            filters={"custom_branch_status": ["is", "set"]}, 
            fields=["name", "custom_bhf_id", "custom_tpin"]
        )
        for b in allowed_branches:
            b["is_default"] = 0
    else:
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

    if not allowed_branches:
        return {"branches_setup": False}

    # 2. PRE-FLIGHT CHECK: Return the active cache state, but ALWAYS include the populated branch choices array!
    cached_branch_id = frappe.cache().hget(hash_key, "custom_active_branch")
    if cached_branch_id:
        return {
            "branches_setup": True,
            "auto_selected": False,
            "branches": allowed_branches,  # FIX: Now populated with real options for manual click dialogs
            "active_branch_name": frappe.cache().hget(hash_key, "custom_active_branch_name"),
            "active_branch_id": cached_branch_id,
            "active_tpin": frappe.cache().hget(hash_key, "custom_tpin")
        }

    # 3. Rule: If user only has one branch total, select it by default instantly
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

    # 4. Rule: Multi-branch sorting (Hoist defaults to index 0)
    allowed_branches.sort(key=lambda x: x.get("is_default", 0), reverse=True)

    return {
        "branches_setup": True,
        "auto_selected": False,
        "branches": allowed_branches
    }
# def get_initial_session_status():
#     user = frappe.session.user
    
#     # 1. Gather all operational branches based on permissions
#     if user == "Administrator":
#         # Administrator bypass: access all active operational branches
#         allowed_branches = frappe.get_all(
#             "Branch", 
#             filters={"custom_branch_status": ["is", "set"]}, 
#             fields=["name", "custom_bhf_id", "custom_tpin"]
#         )
#         # For Admin, we don't force an auto_selected true state unless there is literally 1 branch in system
#         for b in allowed_branches:
#             b["is_default"] = 0
#     else:
#         # Standard User query filtering via the custom_branch_users child table
#         allowed_branches = frappe.db.sql("""
#             SELECT 
#                 b.name, 
#                 b.custom_bhf_id, 
#                 b.custom_tpin, 
#                 bu.is_default
#             FROM `tabBranch` b
#             JOIN `tabBranch User` bu ON bu.parent = b.name
#             WHERE bu.user_id = %s 
#               AND bu.parenttype = 'Branch'
#               AND b.custom_branch_status IS NOT NULL
#         """, (user,), as_dict=True)

#     if not allowed_branches:
#         return {"branches_setup": False}

#     # 2. Rule: If user only has one branch, select it by default instantly
#     if len(allowed_branches) == 1:
#         single_branch = allowed_branches[0]
#         set_branch(single_branch.name, single_branch.custom_bhf_id, single_branch.custom_tpin)
        
#         return {
#             "branches_setup": True,
#             "auto_selected": True,
#             "branches": allowed_branches,
#             "active_branch_name": single_branch.name,
#             "active_branch_id": single_branch.custom_bhf_id,
#             "active_tpin": single_branch.custom_tpin
#         }

#     # 3. Rule: Multi-branch sorting. Sort by is_default descending (1 comes before 0)
#     # This hoists their default branch to index 0
#     allowed_branches.sort(key=lambda x: x.get("is_default", 0), reverse=True)

#     return {
#         "branches_setup": True,
#         "auto_selected": False,
#         "branches": allowed_branches
#     }

# @frappe.whitelist()
# def set_branch(branch_doc_name, branch_id, tpin):
#     """Saves the chosen branch context explicitly using Frappe's native defaults engine."""
#     frappe.defaults.set_user_default("custom_active_branch", branch_id)
#     frappe.defaults.set_user_default("custom_active_branch_name", branch_doc_name)
#     frappe.defaults.set_user_default("custom_tpin", tpin)
#     frappe.db.commit()

#     return {
#         "branch_id": branch_id,
#         "branch_display_name": branch_doc_name,
#         "tpin": tpin
#     }
    
@frappe.whitelist()
def set_branch(branch_doc_name, branch_id, tpin):
    """Saves the chosen branch context dynamically inside the active user's Redis hash map."""
    user_id = frappe.session.user  # Dynamic user name (e.g., 'api@x.com')
    hash_key = f"session_branch:{user_id}"

    # Store variables cleanly as sub-fields inside the user's dedicated hash key map
    frappe.cache.hset(hash_key, "custom_active_branch", branch_id)
    frappe.cache.hset(hash_key, "custom_active_branch_name", branch_doc_name)
    frappe.cache.hset(hash_key, "custom_tpin", tpin)

    return {
        "branch_id": branch_id,
        "branch_display_name": branch_doc_name,
        "tpin": tpin
    }

@frappe.whitelist()
def clear_session_branch_cache(login_manager=None):
    """Explicitly deletes the user's branch context hash when they log out."""
    user = login_manager.user if login_manager else frappe.session.user
    if user:
        frappe.cache.hdel(f"session_branch:{user}", "custom_active_branch")
        frappe.cache.hdel(f"session_branch:{user}", "custom_active_branch_name")
        frappe.cache.hdel(f"session_branch:{user}", "custom_tpin")