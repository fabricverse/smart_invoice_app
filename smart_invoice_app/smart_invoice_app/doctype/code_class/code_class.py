# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from smart_invoice_app.app import api_date_format
from datetime import datetime


class CodeClass(Document):
	def validate(self):
		# date = api_date_format(self.creation)
		# frappe.throw(date)
		pass
	def on_update(self):
		self.update_children()
	
	def update_child_codes(self):
		frappe.msgprint("update_children")
