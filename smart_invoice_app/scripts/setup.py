import frappe

from smart_invoice_app.scripts.branch import (
    check_branches_setup,
    get_branch_code_by_name,
)


@frappe.whitelist()
def check_setup():
    branches_setup = check_branches_setup()

    fully_setup = branches_setup == True
    return {"system_is_setup": fully_setup, "branches_setup": branches_setup}


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
            fields=[
                "name as branch_doc_name",
                "custom_bhf_id as branch_code",
                "custom_tpin as tpin",
                "custom_company as company",
            ],
        )
        for b in allowed_branches:
            b["is_default"] = 0
    else:
        allowed_branches = frappe.db.sql(
            """
            SELECT
                b.name as branch_doc_name,
                b.custom_bhf_id as branch_code,
                b.custom_tpin as tpin,
                b.custom_company as company,
                bu.is_default
            FROM `tabBranch` b
            JOIN `tabBranch User` bu ON bu.parent = b.name
            WHERE bu.user_id = %s
              AND bu.parenttype = 'Branch'
              AND b.custom_branch_status IS NOT NULL
        """,
            (user,),
            as_dict=True,
        )

    if not allowed_branches:
        return {"branches_setup": False}

    # 2. PRE-FLIGHT CHECK: Return the active cache state, but ALWAYS include the populated branch choices array!
    branch_code = frappe.cache().hget(hash_key, "branch_code")
    if branch_code:
        return {
            "branches_setup": True,
            "auto_selected": False,
            "branches": allowed_branches,  # FIX: Now populated with real options for manual click dialogs
            "branch_doc_name": frappe.cache().hget(hash_key, "branch_doc_name"),
            "branch_code": branch_code,
            "tpin": frappe.cache().hget(hash_key, "tpin"),
            "company": frappe.cache().hget(hash_key, "company"),
        }

    # 3. Rule: If user only has one branch total, select it by default instantly
    if len(allowed_branches) == 1:
        single_branch = allowed_branches[0]
        # FIX: single_branch.name was throwing an error here because the SQL field mapping was aliased as branch_doc_name!
        set_branch(
            branch_doc_name=single_branch.branch_doc_name,
            branch_code=single_branch.branch_code,
            tpin=single_branch.tpin,
            company=single_branch.company,
        )

        return {
            "branches_setup": True,
            "auto_selected": True,
            "branches": allowed_branches,
            "branch_doc_name": single_branch.branch_doc_name,
            "branch_code": single_branch.branch_code,
            "tpin": single_branch.tpin,
            "company": single_branch.company,
        }

    # 4. Rule: Multi-branch sorting (Hoist defaults to index 0)
    allowed_branches.sort(key=lambda x: x.get("is_default", 0), reverse=True)

    return {
        "branches_setup": True,
        "auto_selected": False,
        "branches": allowed_branches,
    }


@frappe.whitelist()
def set_branch(branch_doc_name, branch_code, tpin, company):
    """Saves the chosen branch context dynamically inside the active user's Redis hash map."""
    user_id = frappe.session.user  # Dynamic user name (e.g., 'api@x.com')
    hash_key = f"session_branch:{user_id}"

    # Force Frappe's global fallback handler to recognize the newly selected company
    frappe.defaults.set_user_default("company", company, frappe.session.user)

    # Store variables cleanly as sub-fields inside the user's dedicated hash key map
    frappe.cache.hset(hash_key, "branch_code", branch_code)
    frappe.cache.hset(hash_key, "branch_doc_name", branch_doc_name)
    frappe.cache.hset(hash_key, "tpin", tpin)
    frappe.cache.hset(hash_key, "company", company)

    return {
        "branch_code": branch_code,
        "branch_doc_name": branch_doc_name,
        "tpin": tpin,
        "company": company,
    }


@frappe.whitelist()
def clear_session_branch_cache(login_manager=None):
    """Explicitly deletes the user's branch context hash when they log out."""
    user = login_manager.user if login_manager else frappe.session.user
    if user:
        frappe.cache.hdel(f"session_branch:{user}", "branch_code")
        frappe.cache.hdel(f"session_branch:{user}", "branch_doc_name")
        frappe.cache.hdel(f"session_branch:{user}", "tpin")
        frappe.cache.hdel(f"session_branch:{user}", "company")
