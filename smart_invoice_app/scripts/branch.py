import frappe

def test_branches(branch, method):
    print('get_branch_name_by_code', get_branch_name_by_code())
    print('get_branch_name_by_code', get_branch_name_by_code("001"))
    print('get_branch_code_by_name', get_branch_code_by_name(get_branch_name_by_code()))
    print('get_branch_doc', get_branch_doc(get_branch_name_by_code()))
    print('get_branch_vsdc', get_branch_vsdc("000"))
    #, assertEqual(get_branch_vsdc("000"), "2295829289_VSDC"))
    print('check_branches_setup', check_branches_setup())
    
@frappe.whitelist()
def get_branches_with_setup():
    branches = frappe.get_all("Branch", filters={
        "custom_bhf_id": ["is", "set"],
        "custom_bhf_stts_cd": ["is", "set"]
    }, fields=["name"])
    return branches

def check_branches_setup():
    """
    Checks if any branch has setup values.

    :return: True if any branch has setup values, otherwise None.
    """
    branch_list = get_branches_with_setup()
    
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