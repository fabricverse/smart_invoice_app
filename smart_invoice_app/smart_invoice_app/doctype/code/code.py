# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from frappe.model.document import Document


class Code(Document):
	def validate(self):
		self.attempt_code_mapping()
	
	def attempt_code_mapping(self):
		if not self.mapped_doctype or (self.mapped_doctype != "UOM" and self.mapped_entry):
			return
		
		map_entry = self.find_mapping_entry()

		if map_entry:
			self.mapped_entry = map_entry
			frappe.msgprint(f"Mapped {self.mapped_doctype}: {map_entry} for ZRA Code {self.cd_nm}", alert=True)			
		else:
			frappe.msgprint(f"Failed to auto map ZRA Code ({self.cd_nm}) to any {self.mapped_doctype}. You have to map it manually", alert=True)
			

	def get_code_field(self):
		try:
			doctype_fields = frappe.get_meta(self.mapped_doctype).fields
			
			# Get custom fields for the doctype
			custom_fields = frappe.get_all("Custom Field",	filters={"dt": self.mapped_doctype}, fields=["fieldname"], limit=0)

			# Combine standard and custom fields
			all_fields = doctype_fields + [frappe._dict(f) for f in custom_fields]
			print('all_fields', all_fields)
			
			# Find a field that ends with 'cd', '_cd', or '_code'
			return next((field for field in all_fields if field.fieldname.lower().endswith(('_cd', 'cd', 'code'))), None)
		except Exception as e:
			frappe.log_error(f"Error in get_code_field: {str(e)}")
			return None
	
	def find_mapping_entry(self):
		if self.mapped_doctype in ['UOM']:
			try:
				mapped_uom = self.find_db_entry('uom_name', 'custom_cd')
				if mapped_uom:
					# update different fields
					if (mapped_uom[0]['custom_cd'] != self.name or 
						mapped_uom[0]['custom_code_cd'] != self.cd or 
						mapped_uom[0]['custom_code_class_name'] != self.cd_cls):		

						uom_doc = frappe.get_doc("UOM", mapped_uom[0]['uom_name'])
						uom_doc.custom_cd = self.name
						uom_doc.custom_code_cd = self.cd
						uom_doc.custom_code_class_name = self.cd_cls
						uom_doc.flags.ignore_mandatory = True
						uom_doc.save(ignore_permissions=True)
					
					return mapped_uom[0]['uom_name']
				else:
					return self.create_uom_entry().uom_name
			except Exception as e:
				frappe.throw(str(e))
		if self.mapped_doctype in ['Tax Category']:
			tax_category =	 self.find_db_entry('title', 'custom_cd')
			if tax_category:
				# Check if the custom_cd needs to be updated
				if tax_category[0]['custom_cd'] != self.cd:
					doc = frappe.get_doc("Tax Category", tax_category[0]['title'])
					doc.custom_cd = self.cd
					doc.save(ignore_permissions=True)
					
				return tax_category[0]['title']
			else:
				return self.create_tax_category_entry().title
		if self.mapped_doctype in ['Item Tax Template']:
			item_tax_template = self.find_db_entry('title', 'custom_code')
			if item_tax_template:
				return item_tax_template[0]['title']
			else:
				return self.create_item_tax_template_entry()
		if self.mapped_doctype in ['Country']:
			country = self.find_db_entry('country_name', 'code')
			if country:
				return country[0]['country_name']
			else:
				return self.create_country_entry().country_name
		if self.mapped_doctype in ['Sale category']:
			return None
		if self.mapped_doctype in ['Mode of Payment', "Branch"]:
			# set from the doctype
			return None
		else:
			frappe.msgprint(f"No mapping found for {self.mapped_doctype}. You have to map it manually", alert=True)

	def create_item_tax_template_entry(self):
		
		company = frappe.get_cached_doc("Company", frappe.defaults.get_user_default('company'))
		self.create_item_taxes(company)
		last_doc = frappe.get_last_doc("Item Tax Template")
		return last_doc.name

	def create_item_taxes(self, company):
		from smart_invoice_app.app import ensure_tax_accounts

		abbr = company.abbr
		template = frappe.get_all("Item Tax Template", filters={"custom_code": self.cd})
		if template:	
			return template[0]['name']

		ensure_tax_accounts([self], company.name, abbr)

		item_tax = frappe.new_doc("Item Tax Template")
		item_tax.title = self.cd_nm
		item_tax.custom_smart_invoice_tax_code = self.name
		item_tax.company = company.name
		
		# Create a child table row for taxes
		item_tax.append("taxes", {
			"tax_type": f"{self.cd} - {abbr}",
			"tax_rate": flt(self.user_dfn_cd1 or 0.0)
		})

		item_tax.flags.ignore_permissions = True
		item_tax.flags.ignore_mandatory = True		
		item_tax.insert()
		
		title = f"{self.cd_nm} - {abbr}"

		return title

	def create_uom_entry(self):
		# If no match found, create a new document
		new_doc = frappe.new_doc(self.mapped_doctype)
		
		# Determine which field(s) to use
		
		new_doc.uom_name = self.cd_nm
		new_doc.custom_cd = self.name
		new_doc.enabled = 1

		new_doc.insert(ignore_permissions=True, ignore_mandatory=True)
		return new_doc
	
	def create_country_entry(self):
		# If no match found, create a new document
		new_doc = frappe.new_doc(self.mapped_doctype)
		
		# Determine which field(s) to use
		
		new_doc.country_name = self.cd_nm
		new_doc.custom_cd = self.cd

		new_doc.insert(ignore_permissions=True, ignore_mandatory=True)
		return new_doc
	
	def create_tax_category_entry(self):
		# If no match found, create a new document
		new_doc = frappe.new_doc(self.mapped_doctype)
		
		# Determine which field(s) to use
		
		new_doc.title = self.cd_nm
		new_doc.disabled = 0
		new_doc.custom_cd = self.cd

		new_doc.insert(ignore_permissions=True, ignore_mandatory=True)
		return new_doc

	def find_db_entry(self, name_field, custom_field=None):
		conditions = [
			f"{name_field} = %s",
			f"LOWER({name_field}) = LOWER(%s)"
		]
		
		if custom_field:
			conditions.extend([
				f"{custom_field} = %s",
				f"LOWER({custom_field}) = LOWER(%s)"
			])

		query = f"""
			SELECT *
			FROM `tab{self.mapped_doctype}`
			WHERE {' OR '.join(conditions)}
			LIMIT 1
		"""

		params = [
			self.cd_nm,         # Exact match
			self.cd_nm.lower()  # Case-insensitive match
		]
		
		if custom_field:
			params.extend([
				self.cd,        # Exact match with custom field
				self.cd.lower() # Case-insensitive match with custom field
			])
		
		return frappe.db.sql(query, tuple(params), as_dict=True)


	def get_key_from_map_entry(self, map_entry):
		if not map_entry or not isinstance(map_entry[0], dict):
			return None
		return next(iter(map_entry[0]))
