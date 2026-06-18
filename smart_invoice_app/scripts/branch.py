import json

import frappe


def test_branches(branch, method):
    print("get_branch_name_by_code", get_branch_name_by_code())
    print("get_branch_name_by_code", get_branch_name_by_code("001"))
    print("get_branch_code_by_name", get_branch_code_by_name(get_branch_name_by_code()))
    print("get_branch_doc", get_branch_doc(get_branch_name_by_code()))
    print("get_branch_vsdc", get_branch_vsdc("000"))
    # , assertEqual(get_branch_vsdc("000"), "2295829289_VSDC"))
    print("check_branches_setup", check_branches_setup())


@frappe.whitelist()
def get_fully_branches_setup():
    branches = frappe.get_all(
        "Branch",
        filters={"custom_bhf_id": ["is", "set"], "custom_bhf_stts_cd": ["is", "set"]},
        fields=["name", "custom_bhf_id", "custom_tpin"],
    )
    return branches


def check_branches_setup():
    """
    Checks if any branch has setup values.

    :return: True if any branch has setup values, otherwise None.
    """
    branch_list = get_fully_branches_setup()

    return bool(branch_list)


def get_branch_name_by_code(branch_id="000"):
    branch_list = frappe.get_all(
        "Branch", filters={"custom_bhf_id": branch_id}, limit=1, pluck="name"
    )
    if branch_list:
        return branch_list[0]


def get_branch_vsdc(id):
    if not id:
        return
    branch_list = frappe.get_all(
        "Branch",
        fields=["custom_vsdc_serial"],
        filters={"custom_bhf_id": id},
        limit=1,
        pluck="custom_vsdc_serial",
    )
    if branch_list:
        return branch_list[0]


def get_branch_code_by_name(name):
    if not name:
        return
    return frappe.get_cached_value("Branch", name, "custom_bhf_id")


def get_branch_doc(name):
    if not name:
        return
    return frappe.get_cached_doc("Branch", name)


@frappe.whitelist()
def check_default_branch_conflicts(current_branch, child_table_rows, company=None):
    """called from branch client script"""
    if isinstance(child_table_rows, str):
        child_table_rows = json.loads(child_table_rows)

    default_users = [
        row.get("user_id")
        for row in child_table_rows
        if (row.get("is_default") == 1 or row.get("is_default") is True)
        and row.get("user_id")
    ]

    # If it is STILL empty (e.g., a brand new unsaved branch with no company picked), abort safely
    if not default_users or not company:
        return {"has_conflicts": False, "conflicts": []}

    # Direct database scan matching by user, active default state, and shared company
    conflicts = frappe.db.sql(
        """
        SELECT bu.parent as branch, bu.user_id, b.custom_company
        FROM `tabBranch User` bu
        JOIN `tabBranch` b ON b.name = bu.parent
        WHERE bu.user_id IN %s
          AND bu.parenttype = 'Branch'
          AND bu.is_default = 1
          AND bu.parent != %s
          AND b.custom_company = %s
    """,
        (tuple(default_users), current_branch or "NEW_RECORD", company),
        as_dict=True,
    )

    if conflicts:
        return {"has_conflicts": True, "conflicts": conflicts}

    return {"has_conflicts": False, "conflicts": []}


@frappe.whitelist()
def resolve_and_save_branch_conflicts(current_branch, user_ids, company):
    """
    Pass 2: Strip the default status from old branches for the confirmed users,
    scoped strictly to the target company layout.
    """
    if isinstance(user_ids, str):
        user_ids = json.loads(user_ids)

    if not user_ids or not company:
        return {"success": True}

    # Clear default settings only on branches matching this specific company profile context
    frappe.db.sql(
        """
        UPDATE `tabBranch User` bu
        JOIN `tabBranch` b ON b.name = bu.parent
        SET bu.is_default = 0
        WHERE bu.user_id IN %s
          AND bu.parenttype = 'Branch'
          AND bu.parent != %s
          AND b.custom_company = %s
    """,
        (tuple(user_ids), current_branch or "NEW_RECORD", company),
    )

    frappe.db.commit()
    return {"success": True}
