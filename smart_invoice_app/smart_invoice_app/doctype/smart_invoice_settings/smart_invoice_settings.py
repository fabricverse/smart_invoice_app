# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from smart_invoice_app.app import update_codes


class SmartInvoiceSettings(Document):
	def on_update(self):
		update_codes()
	"""
	run test
	update codes
	"""
		
