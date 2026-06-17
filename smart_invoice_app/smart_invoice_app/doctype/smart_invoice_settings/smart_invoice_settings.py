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
        self.initialize_doc()

    @frappe.whitelist()
    def initialize_doc(self):
        pass
        # if self.use_custom_server == 0 or not self.base_url:
        #     site_url = frappe.utils.get_url()
        #     if self.base_url != site_url:
        #         self.base_url = site_url
        # if not self.tpin:
        #     default_company = frappe.defaults.get_user_default("Company")
        #     self.tpin = get_default_company_tpin()

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
