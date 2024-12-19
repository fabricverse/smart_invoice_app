import frappe
from smart_invoice_app.app import get_country_code
from frappe.utils import flt

def execute(filters=None):

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_data(filters):
    company = filters.get('company')
    if not company:
        frappe.throw("Please pick a company first")
    conditions = ["si.docstatus = 1"]  # Only submitted documents

    if filters.get('from_date'):
        conditions.append(f"si.posting_date >= '{filters.get('from_date')}'")
    if filters.get('to_date'):
        conditions.append(f"si.posting_date <= '{filters.get('to_date')}'")
    
    if filters.get('company'):
        conditions.append(f"si.company = '{company}'")
    if filters.get('customer'):
        conditions.append(f"si.customer = '{filters.get('customer')}'")
        
    conditions_sql = " AND ".join(conditions)
    if conditions_sql:
        conditions_sql = "WHERE " + conditions_sql

    data = []
    sql_data = frappe.db.sql(f"""
        SELECT si.name, si.posting_date, si.customer, 
        si.currency, si.conversion_rate, si.tax_id, i.description, 
        i.base_amount, i.item_tax_template

        FROM `tabSales Invoice` as si
        LEFT JOIN `tabSales Invoice Item` as i
        ON si.name = i.parent
        {conditions_sql}
        ORDER BY si.posting_date DESC
    """, as_dict=1)

    if sql_data:
        data = calculate_taxes(sql_data, company)

    return data

def calculate_taxes(data, company):
    processed_items = []
    company = frappe.get_cached_doc("Company", company)

    for row in data:
        
        invoice = frappe.get_cached_doc("Sales Invoice", row.name)
        invoice_country_code = get_country_code(invoice)
        item_tax_template, tax_rate = get_tax_rate(row.item_tax_template, company, invoice_country_code, invoice)

        if tax_rate == 0:
            tax_amt = 0
        else:
            amt = row.base_amount
            rate = (flt(tax_rate/100) + 1)
            taxable_amount = flt(amt/rate, 4)
            tax_amt = flt(amt - taxable_amount, 4)
        row.update({'tax_amount': tax_amt})
        row.update({'item_tax_template': item_tax_template})
        processed_items.append(row)

    if processed_items:
        data = processed_items

    return data

def get_tax_rate(item_tax_template, company, country_code, invoice):
    """ Use normal tax template for item or export tax template for exports """

    item_tax_template = item_tax_template
    tax_rate = 0

    if not item_tax_template:
        tax_code = company.custom_tax_code
        if not tax_code:
            frappe.throw(f"Set <strong>Tax Bracket</strong> in company <a href='{company.get_url()}'>{frappe.bold(ledger.company)}</a>")

        code_doc = frappe.get_cached_value("Code", {"cd": tax_code}, ["name", "cd_nm", "user_dfn_cd1"], as_dict=True)
        tax_rate = flt(code_doc.user_dfn_cd1, 2)
        item_tax_template = f"{code_doc.cd_nm} - {company.abbr}"

    if (invoice.po_no and invoice.custom_validate_lpo == 1):
        item_tax_template = f"Zero-rating LPO - {company.abbr}"
    elif country_code and country_code != "ZM":
        export_tax_template = f"Exports(0%) - {company.abbr}"
        item_tax_template = export_tax_template   
    

    doc = frappe.get_cached_doc("Item Tax Template", item_tax_template)
    tax_rate = flt(doc.taxes[0].tax_rate, 3)

    return item_tax_template, tax_rate



def get_columns():
    columns = [

        # Start of Selection
        {
            "label": "Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 115
        },
        {
            "label": "TPIN",
            "fieldname": "tax_id",
            "fieldtype": "Data",
            "width": 115
        },
        {
            "label": "Customer",
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 190
        },
        {
            "label": "Invoice",
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 190
        },
        {
            "label": "Item Description",
            "fieldname": "description",
            "fieldtype": "Data",
            "width": 340
        },
        {
            "label": "Tax Type",
            "fieldname": "item_tax_template",
            "fieldtype": "data",
            "width": 170
        },
        {
            "label": "Value",
            "fieldname": "base_amount",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": "Tax Amount",
            "fieldname": "tax_amount",
            "fieldtype": "Currency",
            "width": 150
        }
    ]
    return columns
