import frappe
import json

def test_branches(branch, method):
    print('get_branch_name_by_code', get_branch_name_by_code())
    print('get_branch_name_by_code', get_branch_name_by_code("001"))
    print('get_branch_code_by_name', get_branch_code_by_name(get_branch_name_by_code()))
    print('get_branch_doc', get_branch_doc(get_branch_name_by_code()))
    print('get_branch_vsdc', get_branch_vsdc("000"))
    #, assertEqual(get_branch_vsdc("000"), "2295829289_VSDC"))
    print('check_branches_setup', check_branches_setup())
    
@frappe.whitelist()
def get_fully_branches_setup():
    branches = frappe.get_all("Branch", filters={
        "custom_bhf_id": ["is", "set"],
        "custom_bhf_stts_cd": ["is", "set"]
    }, fields=["name", "custom_bhf_id", "custom_tpin"])
    return branches

def check_branches_setup():
    """
    Checks if any branch has setup values.

    :return: True if any branch has setup values, otherwise None.
    """
    branch_list = get_fully_branches_setup()
    
    return bool(branch_list)

def get_branch_name_by_code(branch_id="000"):
    branch_list = frappe.get_all("Branch", filters={"custom_bhf_id": branch_id}, limit=1, pluck="name")
    if branch_list:
        return branch_list[0]

def get_branch_vsdc(id):
    if not id: return
    branch_list = frappe.get_all("Branch", fields=['custom_vsdc_serial'], filters={"custom_bhf_id": id}, limit=1, pluck="custom_vsdc_serial")
    if branch_list:
        return branch_list[0]

def get_branch_code_by_name(name):
    if not name: return
    return frappe.get_cached_value("Branch", name, 'custom_bhf_id')

def get_branch_doc(name):
    if not name: return
    return frappe.get_cached_doc("Branch", name)


@frappe.whitelist()
def check_default_branch_conflicts(current_branch, child_table_rows):
    """
    Pass 1: Inspects the incoming rows for default conflicts across other branches.
    Returns a structured list of conflicts without raising a validation error.
    """
    if isinstance(child_table_rows, str):
        child_table_rows = json.loads(child_table_rows)

    # Filter out only rows where is_default is checked and a user is selected
    default_users = [
        row.get("user_id") for row in child_table_rows 
        if (row.get("is_default") == 1 or row.get("is_default") is True) and row.get("user_id")
    ]

    if not default_users:
        return {"has_conflicts": False, "conflicts": []}

    # Direct database scan across all other branches
    conflicts = frappe.db.sql("""
        SELECT bu.parent as branch, bu.user_id
        FROM `tabBranch User` bu
        WHERE bu.user_id IN %s 
          AND bu.parenttype = 'Branch'
          AND bu.is_default = 1
          AND bu.parent != %s
    """, (tuple(default_users), current_branch or "NEW_RECORD"), as_dict=True)

    if conflicts:
        return {"has_conflicts": True, "conflicts": conflicts}
        
    return {"has_conflicts": False, "conflicts": []}


@frappe.whitelist()
def resolve_and_save_branch_conflicts(current_branch, user_ids):
    """
    Pass 2: Atomic resolution transaction.
    Strips the default status from old branches for the confirmed users.
    """
    if isinstance(user_ids, str):
        user_ids = json.loads(user_ids)

    if not user_ids:
        return {"success": True}

    # Strip default status from all conflicting records across other branches
    frappe.db.sql("""
        UPDATE `tabBranch User`
        SET is_default = 0
        WHERE user_id IN %s 
          AND parenttype = 'Branch'
          AND parent != %s
    """, (tuple(user_ids), current_branch or "NEW_RECORD"))
    
    # Commit changes safely before returning control
    frappe.db.commit()
    return {"success": True}