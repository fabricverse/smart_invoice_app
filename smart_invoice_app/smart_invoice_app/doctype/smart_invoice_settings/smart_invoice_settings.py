# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from smart_invoice_api.api import initialize_vsdc as api_initialize_vsdc

from smart_invoice_app.app import (
    get_function_name,
    is_migration,
)


class SmartInvoiceSettings(Document):
    def on_update(self):
        # Check if the update is triggered by a migration
        if is_migration() or self.initialized == 1:
            return

        self.initialize_virtual_device()

    def validate(self):
        self.set_company_tax_id()

    def set_company_tax_id(self):
        company = frappe.get_cached_doc("Company", self.company)
        if not company.tax_id or company.tax_id != self.tpin:
            company.db_set({"tax_id": self.tpin})
            company.reload()

    @frappe.whitelist()
    def initialize_virtual_device(self):

        api_initialize_vsdc(
            {
                "bhf_id": "000",
                "default_server": self.base_url,
                "environment": self.environment,
                "tpin": self.tpin,
                "vsdc_serial": self.vsdc_serial,
            },
            {
                "function": get_function_name(),
                "doctype": self.doctype,
                "entry": self.name,
                "creator": self.owner,
                "modifier": self.modified_by,
                "company": self.company,
            },
        )

    @frappe.whitelist()
    def get_environments(self):
        envs = frappe.get_all("Environment", fields=["name", "base_url"])
        return {d["name"]: d["base_url"] for d in envs}

    @frappe.whitelist()
    def auto_check_branches_have_users(self):
        if self.branches_have_users() == 1 and self.branches_setup == 0:
            self.branches_setup = 1
            self.status = "Active"
            self.save()
            self.reload()

    def branches_have_users(self):
        """checks if any of the company's branches have no users"""
        branches = frappe.get_all(
            "Branch", filters={"custom_company": self.company}, pluck="name"
        )

        for branch in branches:
            branch = frappe.get_cached_doc("Branch", branch)
            if len(branch.custom_branch_users) < 1:
                # this branch has no users
                return 0
        # all do
        return 1
