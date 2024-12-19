# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from smart_invoice_app.app import update_codes, test_connection, is_migration, api, validate_api_response
import json


class SmartInvoiceSettings(Document):
	def on_update(self):
		# Check if the update is triggered by a migration
		if is_migration():
			return
		test_connection()
		self.initialize_vsdc()

	def validate(self):
		site_url = frappe.utils.get_url()

		if self.default_vsdc_url != site_url:
			self.default_vsdc_url = site_url
	
	@frappe.whitelist()
	def initialize_vsdc(self):
		
		response = api("/api/method/smart_invoice_api.api.initialize_vsdc", {
			"bhf_id": "000",
			"default_server": self.default_server,
			"environment": self.environment,
			"tpin": self.tpin,
			"vsdc_serial": self.vsdc_serial
		})

		if response:
			if data:= response.get("response_data"):
				data = json.loads(data)
				if data.get("resultCd") in ["000", "902"]:
					return "Device is initialized"				
				else:
					return data.get("resultMsg")
			else:
				return "No response data. Verify your VSDC Settings."

		else:
			return "Error: {str(response)}"

			# TODO: simplify
		