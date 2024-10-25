# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from smart_invoice_app.app import api_date_format, is_migration
from datetime import datetime
import requests
import inspect


class CodeClass(Document):
	def on_update(self):
		# Check if the update is triggered by a migration
		if is_migration():
			return
		
		code_list = frappe.get_list("Code", filters={"cd_cls": self.name}, fields=["name", "cd_nm", "cd", "mapped_entry", "mapped_doctype"])
		for code in code_list:
			if code.mapped_doctype != self.mapped_doctype:
				code_doc = frappe.get_doc("Code", code.name)
				code_doc.update({
					"mapped_doctype": self.mapped_doctype,
					"mapped_entry": None
				})
				code_doc.flags.ignore_mandatory = True
				code_doc.save(ignore_permissions=True)
				break


			

