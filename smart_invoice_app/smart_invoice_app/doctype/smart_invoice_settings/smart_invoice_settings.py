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
    def onload(self):
        # Always compute the current layout state on load
        self.compute_onboarding_step()

    def validate(self):
        # Compute status during manual saves
        self.compute_onboarding_step()
        self.set_company_tax_id()

    def on_update(self):
        basics_set = bool(
            self.tpin and self.environment and self.vsdc_serial and self.base_url
        )

        if is_migration() or self.initialized == 1 or not basics_set:
            return

        self.initialize_virtual_device()

    def compute_onboarding_step(self):
        """Dynamically calculates the setup progress pipeline."""
        steps = [
            {
                "id": 1,
                "status": "Setup Company & Environment",
                "is_complete": bool(
                    self.tpin
                    and self.base_url
                    and self.company
                    and self.environment
                    and self.vsdc_serial
                ),
                "intro": "<b>Step 1 of 4:</b> Please ensure your TPIN, Company, and Environment settings are configured and saved.",
                "color": "blue",
                "indicator": "gray",  # standard frappe colors: gray, blue, orange, green, red
            },
            {
                "id": 2,
                "status": "Load Parameters",
                "is_complete": frappe.utils.cint(self.loaded_initialization_data) == 1,
                "intro": "<b>Step 2 of 4:</b> Go to <b>Menu > Load Parameters</b> to load Smart Invoice parameters",
                "color": "blue",
                "indicator": "blue",
            },
            {
                "id": 3,
                "status": "Setup Company Defaults",
                "is_complete": bool(
                    self.default_uom
                    and self.default_packing_unit
                    and self.default_item_class
                    and self.default_item_tax
                ),
                "intro": "<b>Step 3 of 4:</b> Specify your default UOM, packing units, and tax templates, then save.",
                "color": "blue",
                "indicator": "blue",
            },
            {
                "id": 4,
                "status": "Setup Branches",
                "is_complete": frappe.utils.cint(self.branches_setup) == 1,
                "intro": (
                    "<div style='display: flex; justify-content: space-between; align-items: center;'>"
                    "<div><b>Step 4 of 4:</b> Almost there! Assign users to your setup branches.</div>"
                    f"<div style='margin-right: 2%;'><a class='btn btn-success btn-sm' target='_blank' href='/app/branch?custom_company={self.company}'>Branch Setup</a></div>"
                    "</div>"
                ),
                "color": "blue",
                "indicator": "blue",
            },
        ]

        # Find the first incomplete milestone
        current_step = next((step for step in steps if not step["is_complete"]), None)

        if current_step:
            self.status = current_step["status"]
            intro_message = current_step["intro"]
            intro_color = current_step["color"]
            indicator_color = current_step["indicator"]

            if current_step["id"] == 4:
                frappe.enqueue(
                    "smart_invoice_app.api.auto_check_branches_have_users", doc=self
                )
        else:
            self.status = "Active"
            intro_message = "Smart Invoice is fully setup. You can test the connection from <b>Menu > Connection Test</b>"
            intro_color = "green"
            indicator_color = "green"

        # CRITICAL FIX: Pass data cleanly to the frontend wrapper object
        self.set_onload(
            "onboarding",
            {
                "intro_message": intro_message,
                "intro_color": intro_color,
                "indicator_color": indicator_color,
            },
        )

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
