# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from smart_invoice_app.app import update_codes, test_connection, is_migration


class SmartInvoiceSettings(Document):
	def on_update(self):
		# Check if the update is triggered by a migration
		if is_migration():
			return
		test_connection()
		
