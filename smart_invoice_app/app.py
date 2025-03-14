
import io
import os
import frappe
from base64 import b64encode
from frappe import _
from datetime import datetime
import requests, json
from frappe.exceptions import AuthenticationError
from requests.exceptions import JSONDecodeError
from frappe.utils import cstr, now_datetime, flt, get_link_to_form
import inspect
from frappe.utils.password import get_decrypted_password, get_encryption_key
import re

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.data import add_to_date, get_time, getdate
from pyqrcode import create as qr_create

from datetime import datetime, date

def api_date_format(date_input, date_only=False):
    if isinstance(date_input, str):
        if not date_only:
            date_input = datetime.strptime(date_input.split('.')[0], "%Y-%m-%d %H:%M:%S")
        else:
            date_input = datetime.strptime(date_input, "%Y-%m-%d")
    elif isinstance(date_input, date):
        # Convert datetime.date to datetime.datetime
        date_input = datetime.combine(date_input, datetime.min.time())
    elif not isinstance(date_input, datetime):
        frappe.throw("Invalid date type")
    
    return date_input.strftime("%Y%m%d%H%M%S") if not date_only else date_input.strftime("%Y%m%d")

frappe.whitelist()
def get_settings():
    return frappe.get_cached_doc("Smart Invoice Settings", "Smart Invoice Settings")

def get_region(company_name):
    return frappe.get_cached_value("Company", company_name, "country")

def create_qr_code(doc, data):
    region = get_region(doc.company)
    if region not in ['Zambia']:
        return

    # if QR Code field not present, create it. Invoices without QR are invalid as per law.
    if not hasattr(doc, 'invoice_qr_code'):
        create_custom_fields({
            doc.doctype: [
                dict(
                    fieldname='invoice_qr_code',
                    label='Smart Invoice QR',
                    fieldtype='Attach Image',
                    read_only=1, no_copy=1, hidden=1,
                    allow_on_submit=1
                )
            ]
        })

    # Don't create QR Code if it already exists
    if doc.invoice_qr_code:
        return
    
    # qr_code = doc.get("invoice_qr_code")
    # if qr_code and frappe.db.exists({"doctype": "File", "file_url": qr_code}):
    #     return

    meta = frappe.get_meta(doc.doctype)

    if "invoice_qr_code" in [d.fieldname for d in meta.get_image_fields()]:

        qr_image = io.BytesIO()
        url = qr_create(data.get("qrCodeUrl"), error='L')
        url.png(qr_image, scale=2, quiet_zone=1)

        name = frappe.generate_hash(doc.name, 5)

        # making file
        filename = f"QRCode-{name}.png".replace(os.path.sep, "__")
        _file = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "is_private": 0,
            "content": qr_image.getvalue(),
            "attached_to_doctype": doc.get("doctype"),
            "attached_to_name": doc.get("name"),
            "attached_to_field": "invoice_qr_code"
        })

        _file.save()

        # assigning to document
        # doc.db_set('invoice_qr_code', _file.file_url)
        # doc.db_set('custom_sdc_id', data.get("sdcId"))
        # doc.db_set('custom_receipt_no', data.get("rcptNo"))

        # doc.db_set('custom_internal_data', data.get("intrlData"))
        # doc.db_set('custom_fiscal_signature', data.get("rcptSign"))
        # doc.db_set('custom_vsdc_date', data.get("vsdcRcptPbctDate"))
        # doc.db_set('custom_mrc_no', data.get("mrcNo"))

        # intrlData, vsdcRcptPbctDate, mrcNo

        doc.db_set({
            'invoice_qr_code': _file.file_url,
            'custom_sdc_id': data.get("sdcId"),
            'custom_receipt_no': data.get("rcptNo"),
            'custom_internal_data': data.get("intrlData"),
            'custom_fiscal_signature': data.get("rcptSign"),
            'custom_vsdc_date': data.get("vsdcRcptPbctDate"),
            'custom_mrc_no': data.get("mrcNo")
        })
        
        doc.notify_update()


def delete_qr_code_file(doc, method=None):
    region = get_region(doc.company)
    if region not in ['Zambia']:
        return

    if hasattr(doc, 'invoice_qr_code'):
        if doc.get('invoice_qr_code'):
            file_doc = frappe.get_list('File', {
                'file_url': doc.get('invoice_qr_code')
            })
            if len(file_doc):
                frappe.delete_doc('File', file_doc[0].name)

def delete_vat_settings_for_company(doc, method=None):
    pass


@frappe.whitelist()
def save_item_composition(bom, method=None, branch=None):
    if not bom:
        return

    if type(bom) == str:
        bom = frappe.get_cached_doc("BOM", bom)

    item_data = []
    for bom_item in bom.items:
        item = {
            "bhfId": "000",
            "itemCd": bom.item,
            "cpstItemCd": bom_item.item_code,
            "cpstQty": float(bom_item.stock_qty)
        }
        item.update(get_doc_user_data(bom))
        response = api("/api/method/smart_invoice_api.api.save_item_composition", item)
        
        item_data.append(validate_api_response(response))
    if len(bom.items) == len(item_data):
        statuses = set(item.get('resultCd') for item in item_data)

        if len(statuses) == 1 and list(statuses)[0]=="000":
            frappe.msgprint("Smart Invoice: Updated", indicator="green", alert=True)
        elif "000" in statuses:
            frappe.msgprint("Smart Invoice: Partial update", indicator="yellow", alert=True)
        else:
            frappe.msgprint("Smart Invoice: Update failure", indicator="red", alert=True)


        
        
    return item_data


def error_handler(error):
    """
    Generic error handler function.
    Shows msgprint only if env = sandbox or if called from test_connection.
    Returns an error dictionary.
    """
    status_code = error.get('status_code', 'ERR')
    message = error.get('message', 'Unexpected error occurred while connecting to VSDC app.')
    response = error.get('response', 'No details provided.')
    
    # Log the error
    frappe.log_error(
        message=f"Error: {status_code} - {message}\nResponse: {response}",
        title="API Call Error"
    )

    # Check if the function is called from test_connection
    called_from_test = any('test_connection' in frame.function for frame in inspect.stack())
    
    # Show msgprint if env is sandbox or if called from test_connection
    if error.get('environment') == 'Sandbox' or called_from_test:
        msg = message if isinstance(status_code, int) else response
        if not error.get('suppress_msgprint'):
            frappe.msgprint(
                msg=str(msg),
                title=f"Error: {status_code}",
                indicator='red',
                #alert=True
            )
    
    return {
        "error": message,
        "status_code": status_code,
        "response": response,
        "environment": error.get('environment')
    }

def api(endpoint, data, initialize=False): 
    settings = get_settings()
    base_url = settings.base_url
    if settings.default_server == 1:
        base_url = settings.default_vsdc_url
    secret = settings.api_secret

    error_messages = {
        400: "Bad Request",
        401: "Authentication failed. Please check your API credentials.",
        403: "Forbidden. Please check your API credentials.",
        404: "API endpoint not found.",
        415: "Make sure <strong>API Server URL</strong> is correct. Verify whether the site uses https or http.\nIf using https, make sure the server has a valid SSL certificate.",
        417: "Invalid request arguments",
        422: "Unprocessable Entity.",
        500: "An Internal Server Error occurred on the target site. Check the logs for more details.",
        894: "Unable to connect to the Smart Invoice Server.",
        899: "Smart Invoice device error."
    }

    try:
        data.update({
            "default_server": settings.default_server,
            "vsdc_serial": settings.vsdc_serial
        })
        branches = []

        if not data.get("bhfId"):
            data.update({
                "bhfId": "000"
            })
        
        if not data.get("tpin"):
            tpin = None
            if not branches:
                branches = get_user_branches()
            if branches:
                for branch in branches:
                    if branch.get("custom_bhf_id") == data.get("bhfId"):
                        tpin =  branch.get("custom_tpin")
            if not tpin:
                tpin = settings.tpin
            data.update({
                "tpin": tpin
            })
                
        
        if initialize:
            data.update({
                "initialize": True
            })
        # Convert data to JSON string
        # Convert input data to a JSON string
        if isinstance(data, str):
            # If data is a string, parse it as JSON and then re-serialize
            # This ensures the string is valid JSON
            json_data = json.dumps(json.loads(data))
        else:
            # If data is not a string (e.g., dict or list), serialize to JSON
            json_data = json.dumps(data)
        
        r = requests.post(base_url + endpoint, data=json_data, headers={
                "Authorization": f'token {settings.api_key}:{secret}',
                "Content-Type": "application/json"
            })
        
        if r.status_code == 200:
            response_json = r.json()
            return response_json.get("message", response_json)
        elif r.status_code == 417:
            if "smart_invoice_api is not installed" in r.text:
                frappe.throw('Smart Invoice API is not installed on the target site')

            if "frappe.exceptions.ValidationError: Encryption key is invalid!" in r.text:
                frappe.throw('Encryption key is invalid on the target site')
                
            else:
                frappe.throw(r.text)
        else:
            error_info = {
                'status_code': r.status_code,
                'message': error_messages.get(r.status_code, cstr(r.text)),
                'response': r.text,
                'environment': settings.environment
            }
            return error_handler(error_info)

    except json.JSONDecodeError as e:
        error_info = {
            'status_code': 'JSONDecodeError',
            'message': f"Invalid JSON data: {str(e)}",
            'response': e,
            'environment': settings.environment
        }
        return error_handler(error_info)
    except frappe.exceptions.AuthenticationError as e:
        error_info = {
            'status_code': "Authentication Error",
            'message': "Verify your API credentials",
            'response': e,
            'environment': settings.environment
        }
        return error_handler(error_info)
    except requests.exceptions.SSLError as e:
        msg = "Make sure the <strong>API Server URL</strong> is correct. Verify whether the site uses https or http.\nIf using https, make sure the server has a valid SSL certificate."
        error_info = {
            'status_code': 'SSL Error',
            'message': msg,
            'response': msg,
            'environment': settings.environment
        }
        return error_handler(error_info)
    except requests.exceptions.InvalidURL as e:
        msg = "Failed to establish a new connection. Make sure the <strong>API Server URL</strong> is correct and your site is reachable."
        error_info = {
            'status_code': 'Connection Error',
            'message': msg,
            'response': msg,
            'environment': settings.environment
        }
        return error_handler(error_info)
    except requests.exceptions.ConnectionError as e:
        msg = "Failed to establish a new connection. Make sure the <strong>API Server URL</strong> is correct and your site is reachable."
        error_info = {
            'status_code': 'Connection Error',
            'message': msg,
            'response': msg,
            'environment': settings.environment
        }
        return error_handler(error_info)
    except Exception as e:
        error_info = {
            'status_code': 'UnexpectedError',
            'message': f"An unexpected error occurred: {str(e)}",
            'response': e,
            'environment': settings.environment
        }
        return error_handler(error_info)

def get_saved_branches():
    branches = frappe.get_all("Branch", fields=["*"], order_by="custom_bhf_id asc", limit=0)
    if not branches:
        branch = frappe.new_doc("Branch")
        branch.custom_bhf_id = "000"
        return [branch]
    return branches

def get_branches(initialize=False): # review

    response = api("/api/method/smart_invoice_api.api.select_branches", {
        "bhf_id": "000"
    }, initialize)

    return validate_api_response(response)


@frappe.whitelist()
def get_purchase_invoices(from_list=False):
    data = get_purchase_invoices_api()
    
    if data and data.get('resultCd', False)=="000":
        invoices = data.get('data', {'saleList': None}).get('saleList')
        if not invoices:
            frappe.msgprint("No new Purchase Invoices", indicator="Blue", alert=True)
            return
        create_purchase_invoices(invoices)
    else:
        if from_list:
            frappe.msgprint("No new Purchase Invoices", indicator="Blue", alert=True)


def create_purchase_invoices(invoices):    
    count = 0
    for invoice in invoices:
        if not frappe.db.exists("Purchase Invoice", { # TODO: add 'not' exists
            "bill_no": invoice.get('spplrInvcNo'), 
            "supplier": invoice.get('spplrNm'), 
            "grand_total": invoice.get('totAmt'), 
        }):
            create_invoice(invoice)
            count+=1
    if count == 0:
        frappe.msgprint("No new Purchase Invoices", indicator="Blue", alert=True)
    elif count == 1:
        frappe.msgprint(f"Downloaded {count} Purchase Invoice", indicator="Green", alert=True)
    else:
        frappe.msgprint(f"Downloaded {count} Purchase Invoice(s)", indicator="Green", alert=True)


def create_invoice(invoice):
    print(invoice)
    tpin = invoice.get("spplrTpin")
    name = invoice.get("spplrNm")
    branch = invoice.get("spplrBhfId")

    default_company = frappe.defaults.get_user_default("Company")
    company = frappe.get_cached_doc("Company", default_company)

    supplier = get_or_create_supplier(tpin, name, branch)

    items = []
    taxes = []
    for i in invoice.get("itemList"):
        item = get_or_create_item(i)
        item.update({
            'rate': i.get('prc'),
            'discount': i.get('dcAmt'),
            'qty': i.get('qty'),
            'amount': i.get('totAmt')
        })    

        if item.get("item_tax_template"):
            tax_template = frappe.get_cached_doc("Item Tax Template", item.get("item_tax_template"))
            tax_map = {tax.tax_type: tax.tax_rate for tax in tax_template.taxes}

            for tax_account, rate in tax_map.items():
                taxes.append({
                    "doctype": "Purchase Taxes and Charges",
                    "charge_type": "On Net Total",
                    "account_head": tax_account,
                    "rate": rate,
                    "set_by_item_tax_template": 1,
                    "included_in_print_rate": 1,
                    "description": tax_template.custom_code
                })

        items.append(item)

    date, time = format_date_time(invoice.get("cfmDt"))
    invoice_date = format_date_only(invoice.get("salesDt"))

    payment_code = invoice.get("pmtTyCd")
    mode_of_payment, cash_bank_account = get_mop_from_code(payment_code)

    inv = frappe.get_doc({
        "doctype": "Purchase Invoice",
        "posting_date": invoice_date,
        "posting_time": time,
        "set_posting_time": 1,
        "supplier": supplier,
        "custom_branch": get_branch_name(),
        "bill_no": invoice.get("spplrInvcNo"),
        "bill_date": invoice_date,
        # "custom_receipt_type_code": invoice.get("rcptTyCd"),
        "custom_branch_id": invoice.get("spplrBhfId"),
        "company": default_company,
        "update_stock": 1 if invoice.get("stockRlsDt") else 0,
        "items": items,
        "taxes": taxes,
        "disable_rounded_total": 1,
        "custom_downloaded": 1
    })

    if payment_code != "02":
        inv.is_paid = 1
        inv.paid_amount = invoice.get("totAmt")
        inv.mode_of_payment = mode_of_payment
        inv.cash_bank_account = cash_bank_account

    frappe.flags.dont_sync = 1
    inv.insert()
    inv.submit()


def get_branch_name(code="000"):
    br = frappe.get_all("Branch", filters={"custom_bhf_id": code}, fields=["name"], limit=1)
    name = None
    if br:
        name = br[0].name
    return name


def get_mop_from_code(code):
    # TODO: ask user to verify mop
    mop = frappe.db.sql(f"""
            SELECT m.mode_of_payment as name, a.default_account as default_account
            FROM `tabMode of Payment` as m
            LEFT JOIN `tabMode of Payment Account` as a
            ON m.mode_of_payment = a.parent
            WHERE m.custom_cd = "{code}"
            ORDER BY m.enabled DESC
        """, as_dict=1)

    name = code
    default_account = None

    if mop:
        name = mop[0].name
        default_account = mop[0].default_account

    return name, default_account


def format_date_only(datetime_str):
    try:
        date_obj = datetime.strptime(datetime_str, '%Y%m%d')
        formatted_date = date_obj.strftime('%Y-%m-%d')
        return formatted_date
    except (ValueError, TypeError):
        return None

def format_date_time(datetime_str):
    """ Convert datetime string to separate date (dd-mm-yyyy) and time (HH:MM:SS) parts
        Returns tuple of (formatted_date, formatted_time) """
    try:
        date_obj = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
        formatted_date = date_obj.strftime('%Y-%m-%d')
        formatted_time = date_obj.strftime('%H:%M:%S')
        return formatted_date, formatted_time
    except (ValueError, TypeError):
        return None, None

def get_or_create_item(item_data):
    code = item_data.get("itemCd")
    name = item_data.get("itemNm")
    custom_industry_tax_type, tax_code = get_industry_tax_type(item_data)
    itt = get_tax_template_by_tax_code(tax_code)
    uom = get_uom_by_zra_unit(item_data.get("qtyUnitCd"))
    item = frappe.db.sql(
        f"""
            SELECT i.item_code as item_code, i.item_name as item_name, t.item_tax_template as item_tax_template, i.stock_uom as uom
            FROM tabItem as i
            LEFT JOIN `tabItem Tax` as t
            ON i.name = t.parent
            WHERE
                item_code = "{code}" OR
                LOWER(item_name) = "{name.lower()}"
        """, as_dict=1)

    if item:
        return {
            'item_code': item[0].item_code,
            'item_name': item[0].item_name,
            'item_tax_template': itt,
            'uom': uom
        }
    else:
        new = frappe.new_doc("Item")
        new.item_code = item_data.get("itemNm")
        new.item_name = item_data.get("itemNm")

        new.is_stock_item = 1 if item_data.get("pkgUnitCd") else 0
        new.valuation_rate = item_data.get("prc")
        new.item_group = "Products"
        new.custom_item_cls = get_item_class_by_code(item_data.get("itemClsCd"))
        new.country_of_origin = "Zambia" # 
        new.stock_uom = uom
        new.custom_pkg_unit = get_uom_by_zra_unit(item_data.get("pkgUnitCd"))

        new.custom_industry_tax_type = custom_industry_tax_type

        new.append("taxes", {
            "doctype": "Item Tax",
            "item_tax_template": itt
        })

        new.insert(ignore_permissions=True)

        return {
            'item_code': new.item_code,
            'item_name': new.item_name,
            'item_tax_template': itt,
            'uom': new.stock_uom
        }

def get_tax_template_by_tax_code(tax_type):
    temp = frappe.get_all("Item Tax Template", filters={"custom_code": tax_type}, fields=["name", "title"])
    name = None
    if temp:
        name = temp[0].name
    return name


def get_industry_tax_type(item_data=None, tax_code=None):
     
    if not tax_code:
        tax_code = "TOT"   
        if item_data.get("vatAmt") > 0:
            tax_code = item_data.get("vatCatCd")
        elif item_data.get("exciseTaxblAmt") > 0:
            tax_code = item_data.get("exciseTxCatCd")
        elif item_data.get("iplTaxblAmt") > 0:
            tax_code = item_data.get("iplCatCd")
        elif item_data.get("tlTaxblAmt") > 0:
            tax_code = item_data.get("tlCatCd")
    
    industry_tax_type_by_tax_code = {
        "TOT": "TOT",
        "A": "VAT",
        "B": "VAT",
        "RVAT": "VAT",
        "C1": "Zero Rated (VAT)",
        "C2": "Zero Rated (VAT)",
        "C3": "Zero Rated (VAT)",
        "E": "Zero Rated (VAT)",
        "D": "Zero Rated (VAT)",
        "ECM": "Excise Duty",
        "EXEEG": "Excise Duty",
        "TL": "Tourism Levy",
        "IPL": "Insurance Premium Levy"
    }
    return industry_tax_type_by_tax_code.get(tax_code), tax_code    


def get_item_class_by_code(code):
    rs = frappe.db.sql(
        f"""
        SELECT item_cls_nm
        FROM `tabItem Class`
        WHERE
            item_cls_cd = "{code}" OR
            item_cls_nm = "{code}"

        """, 
        as_dict=1)
        
    cls = None
    if not rs:
        new_class = frappe.get_doc({
            "doctype": "Item Class",
            "item_cls_cd": code,
            "item_cls_nm": code,
            "item_cls_lvl": None,
            "tax_ty_cd": None,
            "use_yn": 1,
            "mjr_tg_yn": 0
        }).insert(ignore_permissions=True, ignore_mandatory=True)

        cls = new_class.item_cls_nm

    if rs:
        cls = rs[0].item_cls_nm
    return cls

def get_uom_by_zra_unit(zra_unit):    
    rs =  frappe.db.sql(
        f"""
        SELECT uom_name
        FROM `tabUOM`
        WHERE
            custom_code_cd = "{zra_unit}"
        """, 
    as_dict=1)
    uom = None
    if rs:
        uom = rs[0].uom_name
    return uom
    


def get_or_create_supplier(tpin, name, branch):
    supplier = frappe.db.sql(
        f"""
        SELECT name, supplier_name, tax_id, custom_supplier_branch_id
        FROM tabSupplier
        WHERE
            LOWER(supplier_name) = "{name.lower()}" OR 
            tax_id = "{tpin}"
        """, 
    as_dict=1)

    if supplier:
        if not supplier[0].tax_id:
            frappe.db.set_value("Supplier", supplier[0].name, "tax_id", tpin)
            frappe.msgprint(f"Updated TPIN for {supplier[0].supplier_name}", indicator="success", alert=True)

        if not supplier[0].custom_supplier_branch_id:
            frappe.db.set_value("Supplier", supplier[0].name, "custom_supplier_branch_id", branch)
            frappe.msgprint(f"Updated Branch for {supplier[0].supplier_name}", indicator="success", alert=True)

        return supplier[0].name
    else:
        new = frappe.new_doc("Supplier")
        new.supplier_group = "All Supplier Groups"
        new.supplier_name = name
        new.tax_id = tpin
        new.custom_supplier_branch_id = branch
        new.insert(ignore_permissions=True)

        return new.name

def get_purchase_invoices_api():    
    saved_branches = get_saved_branches()
    response = api( "/api/method/smart_invoice_api.api.select_trns_purchase_sales", {
            "bhf_id": saved_branches[0].custom_bhf_id 
        }, 
        initialize=True,
    )
    data = validate_api_response(response)
    return data

def retry_message():
    frappe.msgprint(title="Smart Invoice", msg="Connection Failure. Retrying in the background ...")

def update_purchase_invoice_api(invoice, method=None, branch=None):
    if invoice.custom_updated_status == 1:
        return

    if save_purchase_invoice_api(invoice, method=None, branch=None):
        invoice.update_stock_ledger()
        invoice.db_set({
            "custom_updated_status": 1
        })
        frappe.db.commit()
    else:
        frappe.msgprint(title="Smart Invoice Failure", msg="Please complete this action manually after resolving the issue.")
        frappe.db.rollback()
    

@frappe.whitelist()
def save_purchase_invoice_api(invoice, method=None, branch=None):
    if frappe.flags.dont_sync == 1 or invoice.custom_asycuda == 1:
        frappe.flags.dont_sync = 0
        return

    if not invoice.custom_invoice_status:
        frappe.throw("Please <strong>Accept</strong> or <strong>Reject</strong> the purchase")
    
    invoice_data = get_invoice_data(invoice, branch=branch)    
    endpoint = "/api/method/smart_invoice_api.api.save_purchase"
    save_response = api(endpoint, invoice_data)

    if not validate_api_response(save_response):
        if save_response.get("error", None):
            retry_message()
            return

    invoice_data = save_response.get("response", None)
    if not invoice_data:
        retry_message()
        return
    json_data = json.loads(invoice_data)

    if json_data.get("resultCd") in ["000", "000"]:
        frappe.msgprint("Saved to Smart Invoice", alert=True, indicator="success")
        return True
    else:
        if json_data.get('resultMsg', None):
            frappe.throw(json_data.get('resultMsg'), title=f"Smart Invoice Failure - {json_data.get('resultCd')}")
        elif json_data.get('error', None):
            if json_data.get('error') in ["VSDC Connection Error", "VSDC timeout"]:
                retry_message()
            elif json_data.get('text', None):
                frappe.msgprint(json_data.get('text'), title=f"Smart Invoice Failure")
                frappe.msgprint("This document will be uploaded once connected to smart invoice", title=f"Smart Invoice Failure")

            else:
                frappe.throw(str(json_data), title=f"Smart Invoice Failure")
        else:
            frappe.throw(str(json_data), title=f"Smart Invoice Failure")


def get_invoice_data(invoice, branch=None):
    if isinstance(invoice, str):
        invoice = frappe.get_cached_doc(invoice.doctype, invoice)
    
    if invoice.discount_amount:
        frappe.throw(_("Sorry, invoice level discounting is not yet supported in Smart Invoice. You can set item level discounts instead."), title="Not Supported")
    
    company = frappe.get_cached_doc("Company", invoice.company)
    if invoice.doctype == "Purchase Invoice":
        party = frappe.get_cached_doc("Supplier", invoice.supplier)
    else:
        party = frappe.get_cached_doc("Customer", invoice.customer)
    
    if not branch:
        branch = frappe.get_cached_doc("Branch", invoice.custom_branch)
    if not party.tax_id:
        party_type = "Supplier" if invoice.doctype == "Purchase Invoice" else "Customer"
        form_link = get_link_to_form(party_type, party.name)
        
        frappe.msgprint(
            msg=_("TPIN is required for {0}").format(form_link), 
            title="Smart Invoice",
            raise_exception=frappe.exceptions.MandatoryError
        )
    
    posting_date = invoice.posting_date
    posting_time = invoice.posting_time or "00:00:00"

    posting_date_time = api_date_format(f"{posting_date} {posting_time}") # TODO: Remove after testing
    posting_date_only = api_date_format(posting_date, date_only=True)

    country_code = get_country_code(invoice)
    test_invoice_name = api_date_format(f"{frappe.utils.get_datetime_str(frappe.utils.get_datetime())}")

    if invoice.doctype == "Sales Invoice":
        # Group variables that depend on is_return
        if invoice.is_return == 1:
            original_invoice = frappe.get_cached_doc(invoice.doctype, invoice.return_against)
            rcpt_ty_cd = "R"
            sales_stts_cd = "05"
            org_invc_no = original_invoice.custom_receipt_no
            org_sdc_id = original_invoice.custom_sdc_id
            rfd_rsn_cd = invoice.custom_refund_reason_code
            rfd_dt = None
            if rfd_rsn_cd:
                rfd_dt = api_date_format(f"{posting_date} {posting_time}")
            cancel_date = get_cancel_date(invoice)
        else:
            rcpt_ty_cd = "S"
            sales_stts_cd = "02"
            org_invc_no = 0
            org_sdc_id = None
            rfd_dt = None
            rfd_rsn_cd = ""
            cancel_date = None
        
        data = {
            "custTpin": party.tax_id,
            "custNm": party.customer_name,
            "salesTyCd": "N",  # Assuming normal sale
            "rcptTyCd": rcpt_ty_cd,
            "pmtTyCd": get_payment_code(invoice),
            "salesSttsCd": sales_stts_cd,
            
            "salesDt": posting_date_only,
            "stockRlsDt": None if invoice.update_stock == 0 else posting_date_time,
            "saleCtyCd": "1",
            "prchrAcptcYn": "Y",

            "lpoNumber": invoice.po_no if invoice.custom_validate_lpo == 1 else None,
            "dbtRsnCd": None,
            "invcAdjustReason": None
        }

    else: # if purchase invoice
            
        # Group variables that depend on is_return
        if invoice.is_return == 1:
            rcpt_ty_cd = "R"
            pchsSttsCd = "05"
            org_invc_no = 0
            org_sdc_id = None
            rfd_rsn_cd = invoice.custom_refund_reason_code
            rfd_dt = None
            if rfd_rsn_cd:
                rfd_dt = api_date_format(f"{posting_date} {posting_time}")
            cancel_date = get_cancel_date(invoice)
        else:
            status_options = {
                "Approved": "02",
                "Refunded": "05",
                "Transferred": "06",
                "Rejected": "04"
            }

            pchsSttsCd = status_options.get(invoice.custom_invoice_status, "02")
            rcpt_ty_cd = "P"
            org_invc_no = 0
            org_sdc_id = None
            rfd_dt = None
            rfd_rsn_cd = ""
            cancel_date = None

        data = {
            "spplrTpin": party.tax_id,
            "spplrBhfId": party.custom_supplier_branch_id or "000", 
            "spplrNm": party.supplier_name,
            "spplrInvcNo": invoice.bill_no,
            "regTyCd": "M",
            "pchsTyCd": "N",
            "rcptTyCd": rcpt_ty_cd,
            "pmtTyCd": get_payment_code(invoice),
            "pchsSttsCd": pchsSttsCd,
            "cfmDt": posting_date_time,
            "pchsDt": posting_date_only
        }
    
    data.update({
        "tpin": branch.custom_tpin,
        "bhfId": branch.custom_bhf_id,        
        "orgSdcId": org_sdc_id,
        "orgInvcNo": org_invc_no,
        "cisInvcNo": invoice.name, #test_invoice_name
            
        "rfdDt": rfd_dt,
        "rfdRsnCd": rfd_rsn_cd,
        "totItemCnt": len(invoice.items),

        "cfmDt": posting_date_time,
        "cnclReqDt": cancel_date,
        "cnclDt": cancel_date,
        "remark": invoice.remarks or "",
        "currencyTyCd": invoice.currency or "XXX",
        "exchangeRt": invoice.conversion_rate,
        
        "cashDcAmt": flt(invoice.discount_amount, 3),
        "cashDcRt": flt(invoice.additional_discount_percentage, 3),
        "destnCountryCd": country_code if country_code != "ZM" else None,

        "taxRtA": 16,
        "taxblAmtA": 0.0,
        "taxAmtA": 0.0,
        "taxRtB": 16,
        "taxblAmtB": 0.0,
        "taxAmtB": 0.0,
        "taxRtC1": 0,
        "taxblAmtC1": 0.0,
        "taxAmtC1": 0.0,
        "taxRtC2": 0,
        "taxblAmtC2": 0.0,
        "taxAmtC2": 0.0,
        "taxRtC3": 0,
        "taxblAmtC3": 0.0,
        "taxAmtC3": 0.0,
        "taxRtD": 0,
        "taxblAmtD": 0.0,
        "taxAmtD": 0.0,
        "taxRtRvat": 0,
        "taxblAmtRvat": 0.0,
        "taxAmtRvat": 0.0,
        "taxRtE": 0,
        "taxblAmtE": 0.0,
        "taxAmtE": 0.0,
        "taxRtF": 10,
        "taxblAmtF": 0.0,
        "taxAmtF": 0.0,
        "taxRtTot": 0,
        "taxblAmtTot": 0.0,
        "taxAmtTot": 0.0,

        "taxRtIpl1": 5,
        "taxblAmtIpl1": 0.0,
        "taxAmtIpl1": 0.0,
        "taxRtIpl2": 0,
        "taxblAmtIpl2": 0.0,
        "taxAmtIpl2": 0.0,
        "taxRtTl": 1.5,
        "taxblAmtTl": 0.0,
        "taxAmtTl": 0.0,
        "taxRtEcm": 5,
        "taxblAmtEcm": 0.0,
        "taxAmtEcm": 0.0,
        "taxRtExeeg": 3,
        "taxblAmtExeeg": 0.0,
        "taxAmtExeeg": 0.0,

        "tlAmt": 0.0,
        "totTaxblAmt": 0.0,
        "totTaxAmt": 0.0,
        "totAmt": 0.0,
        "itemList": []
    })
    items = []
    data, items = calculate_item_taxes(company, invoice, data, items, country_code)

    data.update({"itemList": items})
    data.update(get_doc_user_data(invoice)) # add user info

    return data



def calculate_item_taxes(company, invoice, data, items, country_code=None):
    items = []

    for idx, item in enumerate(invoice.items, start=1):

        item_doc = frappe.get_cached_doc("Item", item.item_code)
        unit_cd, pkg_unit = get_unit_code(item_doc, invoice.company)
            
        qty = flt(abs(item.qty), 3)
        price = flt(abs(item.rate), 3)
        amt = flt(abs(item.amount), 3)


        item_data = {
            "itemSeq": idx,
            "itemCd": item.item_code,
            "itemClsCd": item_doc.custom_item_cls_cd or company.custom_default_item_class,
            "itemNm": item.item_code,
            "bcd": None,
            "pkgUnitCd": pkg_unit or "PACK",
            "pkg": qty,
            "qtyUnitCd": unit_cd or "U",
            "qty": qty,
            "prc": price,
            "splyAmt": amt,
            "dcRt": 0.0,
            "dcAmt": 0.0,
            "isrccCd": None,
            "isrccNm": None,
            "rrp": price,
            "isrcRt": 0.0,
            "isrcAmt": 0.0,
            "totDcAmt": 0.0,
            "totAmt": amt,
            "taxblAmt": 0.0,
            "taxAmt": 0.0
        }

        # set tax defaults
        code_doc = None

        template = None
        tax_code = None
        tax_rate = 0


        def get_item_tax_template(item, company, country_code, invoice):
            """ Set normal tax template for item or export tax template for exports """
            if invoice.doctype == "Sales Invoice" and (invoice.po_no and invoice.custom_validate_lpo == 1):
                item.item_tax_template = f"Zero-rating LPO - {company.abbr}"
            elif country_code and country_code != "ZM" and invoice.doctype == "Sales Invoice":
                export_tax_template = f"Exports(0%) - {company.abbr}"
                if item.item_tax_template != export_tax_template:
                    frappe.db.set_value(invoice.doctype + " Item", item.name, "item_tax_template", export_tax_template)
                    for tax in invoice.taxes:
                        tax_doctype = "Sales Taxes and Charges" if invoice.doctype == "Sales Invoice" else "Purchase Taxes and Charges"
                        frappe.delete_doc(tax_doctype, tax.name)
                        frappe.db.set_value(invoice.doctype, invoice.name, "total_taxes_and_charges", 0)

                item.item_tax_template = export_tax_template

            doc = frappe.get_cached_doc("Item Tax Template", item.item_tax_template)

            template = item.item_tax_template
            tax_code = doc.custom_code.title()
            tax_rate = flt(doc.taxes[0].tax_rate, 3)

            return template, tax_code, tax_rate
        
        # get tax code from purchase or sales invoice item
        if item.item_tax_template:                
            template, tax_code, tax_rate = get_item_tax_template(item, company, country_code, invoice)
        else:
            if country_code and country_code != "ZM" and invoice.doctype == "Sales Invoice":
                template, tax_code, tax_rate = get_item_tax_template(item, company, country_code, invoice)
            elif item_doc.taxes:
                # get template from item taxes if not in transaction items
                template = item_doc.taxes[0].item_tax_template
                tax_template = frappe.get_cached_doc("Item Tax Template", template)
                tax_code = tax_template.custom_code.title()
                tax_rate = flt(tax_template.taxes[0].tax_rate, 3)
                
        if not template:
            # use company default company if not set in transation or item
            # TODO: if below doesnt set default company tax, copy logic from get_tax_rate in vat trans report py
            if country_code and country_code != "ZM" and invoice.doctype == "Sales Invoice":
                template, tax_code, tax_rate = get_item_tax_template(item, company, country_code, invoice)
            else:
                tax_code = company.custom_tax_code
                if not tax_code:
                    frappe.throw(f"Set <strong>Tax Bracket</strong> in company <a href='{company.get_url()}'>{frappe.bold(ledger.company)}</a>")

                code_doc = frappe.get_cached_value("Code", {"cd": tax_code}, ["name", "cd_nm", "user_dfn_cd1"], as_dict=True)
                tax_rate = flt(code_doc.user_dfn_cd1, 2)
                template = f"{code_doc.cd_nm} - {company.abbr}"

        # Calculate taxes for the item
        if template in [
            f"Excise Electricity - {company.abbr}",
            f"Excise on Coal - {company.abbr}",
            f"Tourism Levy - {company.abbr}",
            f"Insurance Premium Levy - {company.abbr}",
            f"Re-insurance - {company.abbr}"
        ]:
            tax_types = {
                f"Excise Electricity - {company.abbr}": "excise",
                f"Excise on Coal - {company.abbr}": "excise",
                f"Tourism Levy - {company.abbr}": "tl",
                f"Insurance Premium Levy - {company.abbr}": "ipl",
                f"Re-insurance - {company.abbr}": "ipl"
            }

            amt = flt(abs(amt), 4)
            rate = 0.0
            taxable_amount = 0.0
            tax_amt = 0.0
            
            if tax_rate != 0:
                rate = (flt(tax_rate/100) + 1)
                taxable_amount = flt(amt/rate, 4)
                tax_amt = flt(amt - taxable_amount, 4)

            tax_type = tax_types[template]

            if template in [
                f"Tourism Levy - {company.abbr}",
                f"Insurance Premium Levy - {company.abbr}",
                f"Re-insurance - {company.abbr}"
            ]:
                if tax_code == "Ipl2":
                    taxable_amount = amt

                item_data.update({
                    f"{tax_type}CatCd": tax_code.upper(),
                    f"{tax_type}TaxblAmt": taxable_amount,
                    f"{tax_type}Amt": tax_amt
                })
            elif template in [
                f"Excise Electricity - {company.abbr}",
                f"Excise on Coal - {company.abbr}"
            ]:
                item_data.update({
                    f"{tax_type}TxCatCd": tax_code.upper(),
                    f"{tax_type}TaxblAmt": taxable_amount,
                    f"{tax_type}TxAmt": tax_amt
                })

            inv_taxable_amount = taxable_amount
            inv_tax_amount = tax_amt

            tot_taxbl_amt = taxable_amount
            tot_tax_amt = tax_amt
            inv_tot_amt = amt

            item_data.update({
                f"taxblAmt{tax_code}": flt(inv_taxable_amount, 4),
                f"taxAmt{tax_code}": flt(inv_tax_amount, 4),

                f"taxRt{tax_code}": tax_rate,

                "totTaxblAmt": flt(tot_taxbl_amt, 4),
                "totTaxAmt": flt(tot_tax_amt, 4),
                "totAmt": flt(inv_tot_amt, 4)
            })
        # elif item_doc.custom_industry_tax_type == "Rental Tax": # TODO: implement these tax types
        #     not_supported()
        # elif item_doc.custom_industry_tax_type == "Service Tax":
        #     not_supported()
        else:
            if tax_rate == 0:
                item_taxes = {
                    "totAmt": amt,
                    "vatTaxblAmt": amt,
                    "vatAmt": 0
                }
                
            else:               

                tax_rate = (flt(tax_rate, 4)/100) + 1 if tax_rate else 0.0
                amt = flt(abs(amt), 4)
                
                taxable_amount = flt((amt/tax_rate) if tax_rate != 0 else 0, 4)
                tax_amt = flt(amt - taxable_amount, 4)
                
                item_taxes = {
                    "totAmt": amt,
                    "vatTaxblAmt": taxable_amount,
                    "vatAmt": tax_amt
                }
                
            if tax_code in ["A", "B", "C1", "C2", "C3", "D", "E", "Rvat"]:    
                item_taxes.update({
                    "vatCatCd": tax_code.upper(),
                })
            elif tax_code == "Tot":
                if invoice.doctype == "Sales Invoice":
                    item_taxes.update({
                        "taxCatCd": tax_code.upper(),
                        "taxblAmt": amt,
                        "taxAmt": 0
                    })
                else:
                    item_taxes.update({
                        "taxCatCd": tax_code.upper(),
                        "vatCatCd": "A",
                        "taxblAmt": amt,
                        "taxAmt": 0
                    })

            item_data.update(item_taxes)
            
            # total main doc from each item
            tax_amount = data[f"taxAmt{tax_code}"] + item_taxes.get("vatAmt", 0)
            taxable_amount = data[f"taxblAmt{tax_code}"] + item_taxes.get("vatTaxblAmt", 0)
            total_taxable_amount = data[f"totTaxblAmt"] + item_taxes.get("vatTaxblAmt", 0)
            total_tax_amount = data[f"totTaxAmt"] + item_taxes.get("vatAmt", 0)
            total_amount = data["totAmt"] + item_taxes.get("totAmt", 0)

            data.update({
                f"taxAmt{tax_code}": flt(tax_amount, 4),
                f"taxblAmt{tax_code}": flt(taxable_amount, 4),
                "taxblAmtTot": 0,
                "taxAmtTot": 0,
                "totTaxblAmt": flt(total_taxable_amount, 4),
                "totTaxAmt": flt(total_tax_amount, 4),
                "totAmt": flt(total_amount, 4)
            })
        items.append(item_data)
    return data, items


@frappe.whitelist()
def save_invoice_api(invoice, method=None, branch=None):
    
    invoice_data = get_invoice_data(invoice, branch=branch)    
    endpoint = "/api/method/smart_invoice_api.api.save_sales"
    save_response = api(endpoint, invoice_data)
    
    if save_response.get('error', None):
        error_handler(save_response)
        return
    
    invoice_data = save_response.get("response", None)
    if not invoice_data:
        frappe.msgprint(title="Smart Invoice", msg="Connection Failure. Retrying in the background ...")
        return
    json_data = json.loads(invoice_data)

    if json_data.get("resultCd") == "000":
        frappe.db.commit()
        data = json_data.get("data")
        create_qr_code(invoice, data=data)
    else:
        frappe.db.rollback()
        if "LPO" in json_data.get("resultCd"):
            frappe.throw(json_data.get('resultMsg'), title=f"Smart Invoice Failure - {json_data.get('resultCd')}")
        elif json_data.get('resultMsg', None):
            frappe.throw(json_data.get('resultMsg'), title=f"Smart Invoice Failure - {json_data.get('resultCd')}")
        elif json_data.get('error', None):
            if json_data.get('error') in ["VSDC Connection Error", "VSDC timeout"]:
                frappe.msgprint("Smart Invoice: Connection Failure. Retrying in the background ...")
            elif json_data.get('text', None):
                # frappe.throw(json_data.get('text'), title=f"Smart Invoice Failure")
                frappe.msgprint(json_data.get('text'), title=f"Smart Invoice Failure")
            else:
                frappe.throw(str(json_data), title=f"Smart Invoice Failure")
        else:
            frappe.throw(str(json_data), title=f"Smart Invoice Failure")

from erpnext.stock.stock_ledger import get_stock_balance
def get_stock_master_data(stock_item_data, ledger):
    # balance_qty = get_stock_balance(ledger.item_code, ledger.warehouse)
    balance = frappe.get_cached_value("Bin", {"item_code": ledger.item_code, "warehouse": ledger.warehouse}, "actual_qty") or 0
    operation = "add" if ledger.actual_qty > 0 else "sub"
    if operation == "add":
        balance += abs(ledger.actual_qty)   
    else:
        balance -= abs(ledger.actual_qty)

    stock_master_data = {
        "tpin": stock_item_data.get("tpin"),
        "bhfId": stock_item_data.get("bhfId"),
        "stockItemList": [{
            "itemCd": ledger.item_code,
            "rsdQty": balance
        }]
    }

    stock_master_data.update(get_doc_user_data(ledger)) # add user info
    return stock_master_data

def update_stock_movement(ledger, method=None):

    if ledger.voucher_type == "Purchase Invoice":
        inv = frappe.get_doc(ledger.voucher_type, ledger.voucher_no)
        # dont update stock if status isnt set 
        # OR when the invoice is already uploaded
        if (inv.custom_downloaded == 1 and not inv.custom_invoice_status) or inv.custom_updated_status == 1:
            print("not running stock")
            return
    
    stock_master_data = None
    if stock_item_data := get_item_data(ledger):
        sync_doc = api("/api/method/smart_invoice_api.api.save_stock_items", stock_item_data)
        response = json.loads(sync_doc.get("response"))

        if response.get("resultCd") == "000" or sync_doc.get('status', None) == "Connection Error":
            stock_master_data = get_stock_master_data(sync_doc, ledger)
            
            saved_stock_master = api("/api/method/smart_invoice_api.api.save_stock_master", stock_master_data)
            saved_stock_master_response = json.loads(saved_stock_master.get("response"))

        #     if not saved_stock_master_response or saved_stock_master_response.get("resultCd") != "000":
        #         frappe.msgprint(_(f"Message: {saved_stock_master_response.get('resultMsg')}"), title="Smart Invoice Failure")
        # elif response.get('error', None):
        #     frappe.msgprint(title=response.get("text", response.get('error', "Unknown Error: " + str(response))), msg=response.get('error', None))
        # else:
        #     frappe.msgprint(_(f"Message: {saved_stock_items.get('resultMsg')}"), title="Smart Invoice Failure")


def get_item_data(ledger):
    items = []
    data={}

    item_doc = frappe.get_cached_doc("Item", ledger.item_code)
    unit_cd, pkg_unit = get_unit_code(item_doc, ledger.company)


    posting_date_only = api_date_format(str(ledger.posting_date), date_only=True)
    
    company = frappe.get_cached_doc("Company", ledger.company)

    stock_item_data = {
        "tpin": company.tax_id,
        "bhfId": "000", # TODO: get branch id
        "sarNo": 1,
        "orgSarNo": 0,
        "regTyCd": "M",
        "custTpin": None,
        "custNm": None,
        "custBhfId": "000",
        "sarTyCd": "13", # TODO: if invoice.is_return == 0 else "12",
        "ocrnDt": posting_date_only,
        "totItemCnt": 1,
        "totTaxblAmt": 0,
        "totTaxAmt": 0,
        "totAmt": 0,
        "remark": None,
        "itemList": []
    }
    
    _price = ledger.incoming_rate or ledger.outgoing_rate or ledger.valuation_rate
    
    if not _price:
        item_value = frappe.db.get_value("Item", ledger.item_code, "valuation_rate")
        _price = item_value

    if not _price:        
        form_link = get_link_to_form("Item", ledger.item_code)

        message = _(
            "Valuation Rate for the Item {0}, is required to do accounting entries for {1} {2}."
        ).format(form_link, ledger.voucher_type, ledger.voucher_no)
        message += "<br><br>"
        
        solutions = (
            _("You can Submit this entry")
            + " {} ".format(frappe.bold(_("after")))
            + _("performing either one below:")
        )
        sub_solutions = "<ul><li>" + _("Create an incoming stock transaction for the Item.") + "</li>"
        sub_solutions += "<li>" + _("Set a Valuation Rate for {0}.").format(form_link) + "</li></ul>"
        msg = message + solutions + sub_solutions + "</li>"

        frappe.throw(msg=msg, title=_("Valuation Rate Missing"))
        
    qty = flt(abs(ledger.actual_qty), 3)
    price = flt(abs(_price), 3)
    amt = flt(qty * price, 3)


    item_data = {
        "itemSeq": 1,
        "itemCd": ledger.item_code,
        "itemClsCd": item_doc.custom_item_cls_cd or company.custom_default_item_class,
        "itemNm": ledger.item_code,
        "bcd": None,
        "pkgUnitCd": pkg_unit or "PACK",
        "pkg": qty,
        "qtyUnitCd": unit_cd or "U",
        "qty": qty,
        "prc": price,
        "splyAmt": amt,
        "dcRt": 0.0,
        "dcAmt": 0.0,
        "isrccCd": None,
        "isrccNm": None,
        "rrp": price,
        "isrcRt": 0.0,
        "isrcAmt": 0.0,
        "totDcAmt": 0.0,
        "totAmt": amt,
        "vatCatCd": "A",
        "taxblAmt": 0.0,
        "taxAmt": 0.0
    }

    # set tax defaults
    code_doc = None

    template = None
    tax_code = None
    tax_rate = 0

    # TODO: cancelling transactions needs an adjustment entry
    
    # get tax code from purchase or sales invoice item if its one of these docs
    if ledger.voucher_type in ["Purchase Invoice", "Sales Invoice", "Delivery Note", "Purchase Receipt"]:
        doc = None
        transaction_code = "13"
        """
        01 Import          Incoming - Import
        02 Purchase        Incoming - Purchase
        03 Return          Incoming - Return
        04 Stock Movement  Incoming - Stock Movement
        05 Processing      Incoming - Processing
        06 Adjustment      Incoming - Adjustment
        11 Sale            Outgoing - Sale
        12 Return          Outgoing - Return
        13 Stock Movement  Outgoing - Stock Movement
        14 Processing      Outgoing - Processing
        15 Discarding      Outgoing - Discarding
        16 Adjustment      Outgoing - Adjustment
        """

        if ledger.voucher_type in ["Delivery Note", "Purchase Receipt"]:
            if ledger.voucher_type == "Delivery Note":
                dn = frappe.get_cached_doc("Delivery Note", ledger.voucher_no)
                for item in dn.items:
                    if item.item_code == ledger.item_code:
                        tax_template = item.item_tax_template
                        if item.against_sales_invoice:
                            doc = frappe.get_cached_doc("Sales Invoice", item.against_sales_invoice)
                            break
                
                if dn.is_return == 1:
                    transaction_code = "12"
                else:
                    transaction_code = "11"

                # if cancelled, use opposite transaction code
                if dn.docstatus == 2:
                    if dn.is_return == 1:
                        transaction_code = "11"
                    else:
                        transaction_code = "12"
            else:
                pr = frappe.get_cached_doc("Purchase Receipt", ledger.voucher_no)
                for item in pr.items:
                    if item.item_code == ledger.item_code:
                        tax_template = item.item_tax_template
                        if item.purchase_invoice:
                            doc = frappe.get_cached_doc("Purchase Invoice", item.purchase_invoice)
                            break
                
                if pr.is_return == 1:
                    transaction_code = "03"
                else:
                    if pr.custom_asycuda == 0: 
                        transaction_code = "02"
                    else:
                        transaction_code = "01"

                # if cancelled, use opposite transaction code
                if pr.docstatus == 2:
                    transaction_code = "03"
            
        else:
            doc = frappe.get_cached_doc(ledger.voucher_type, ledger.voucher_no)
            
            if doc.doctype == "Sales Invoice":                
                if doc.is_return == 1:
                    transaction_code = "12"
                else:
                    transaction_code = "11"     

                # if cancelled, use opposite transaction code
                if doc.docstatus == 2:
                    if doc.is_return == 1:
                        transaction_code = "11"
                    else:
                        transaction_code = "12"
            elif doc.doctype == "Purchase Invoice":
                if doc.is_return == 1:
                    transaction_code = "03"
                else:
                    transaction_code = "04"  

                # if cancelled, use opposite transaction code
                if doc.docstatus == 2:
                    if doc.is_return == 1:
                        transaction_code = "04"
                    else:
                        transaction_code = "03"

        if doc or tax_template:
            if not doc:
                doc = frappe.get_cached_doc("Item Tax Template", tax_template)

                template = tax_template
                tax_code = doc.custom_code.title()
                tax_rate = flt(doc.taxes[0].tax_rate, 3)

            else:
                for item in doc.items:
                    if item.item_code == ledger.item_code:
                        template = item_doc.taxes[0].item_tax_template
                        tax_template = frappe.get_cached_doc("Item Tax Template", template)
                        tax_code = tax_template.custom_code.title()
                        tax_rate = flt(tax_template.taxes[0].tax_rate, 3)
        else:
            template = item_doc.taxes[0].item_tax_template
            tax_template = frappe.get_cached_doc("Item Tax Template", template)
            tax_code = tax_template.custom_code.title()
            tax_rate = flt(tax_template.taxes[0].tax_rate, 3)
    else:
        # get template from item taxes if not in transaction items
        template = item_doc.taxes[0].item_tax_template
        tax_template = frappe.get_cached_doc("Item Tax Template", template)
        tax_code = tax_template.custom_code.title()
        tax_rate = flt(tax_template.taxes[0].tax_rate, 3)
        
        if ledger.voucher_type == "Stock Reconciliation":
            transaction_code = "06"
        elif ledger.voucher_type == "Stock Entry":
            se = frappe.get_cached_doc("Stock Entry", ledger.voucher_no)
            if se.stock_entry_type in ["Material Transfer"]:
                # prevent duplication of entries for Stock Transfers
                return None
            
            elif se.stock_entry_type == "Material Issue":
                transaction_code = "16"
                
                # if cancelled, use opposite transaction code
                if se.docstatus == 2:
                    transaction_code = "04"
            elif se.stock_entry_type == "Material Receipt":
                transaction_code = "06"
                
                # if cancelled, use opposite transaction code
                if se.docstatus == 2:
                    transaction_code = "13"

            elif se.stock_entry_type in ["Manufacture", "Repack", "Material Transfer for Manufacture", "Send to Subcontractor"]:
                if ledger.actual_qty > 0:
                    transaction_code = "05"
                else:
                    transaction_code = "14"
                
                # if cancelled, use opposite transaction code
                if se.docstatus == 2:
                    transaction_code = "14"
                else:
                    transaction_code = "05"
            else:
                return None
                
    if not template:
        # use company default company if not set in transation or item
        tax_code = company.custom_tax_code
        if not tax_code:
            frappe.throw(f"Set <strong>Tax Bracket</strong> in company <a href='{company.get_url()}'>{frappe.bold(ledger.company)}</a>")

            code_doc = frappe.get_cached_value("Code", {"cd": tax_code}, ["name", "cd_nm", "user_dfn_cd1"], as_dict=True)
            tax_rate = flt(code_doc.user_dfn_cd1, 2)
            template = f"{code_doc.cd_nm} - {company.abbr}"

    # Calculate taxes for the item
    if template in [
        f"Excise Electricity - {company.abbr}",
        f"Excise on Coal - {company.abbr}",
        f"Tourism Levy - {company.abbr}",
        f"Insurance Premium Levy - {company.abbr}",
        f"Re-insurance - {company.abbr}"
    ]:
        tax_types = {
            f"Excise Electricity - {company.abbr}": "excise",
            f"Excise on Coal - {company.abbr}": "excise",
            f"Tourism Levy - {company.abbr}": "tl",
            f"Insurance Premium Levy - {company.abbr}": "ipl",
            f"Re-insurance - {company.abbr}": "ipl"
        }

        amt = flt(abs(amt), 4)
        rate = 0.0
        taxable_amount = 0.0
        tax_amt = 0.0
        
        if tax_rate != 0:
            rate = (flt(tax_rate/100) + 1)
            taxable_amount = flt(amt/rate, 4)
            tax_amt = flt(amt - taxable_amount, 4)

        tax_type = tax_types[template]

        if template in [
            f"Tourism Levy - {company.abbr}",
            f"Insurance Premium Levy - {company.abbr}",
            f"Re-insurance - {company.abbr}"
        ]:
            if tax_code == "Ipl2":
                taxable_amount = amt

            item_data.update({
                f"{tax_type}CatCd": tax_code.upper(),
                f"{tax_type}TaxblAmt": taxable_amount,
                f"{tax_type}Amt": tax_amt
            })
        elif template in [
            f"Excise Electricity - {company.abbr}",
            f"Excise on Coal - {company.abbr}"
        ]:
            item_data.update({
                f"{tax_type}TxCatCd": tax_code.upper(),
                f"{tax_type}TaxblAmt": taxable_amount,
                f"{tax_type}TxAmt": tax_amt
            })

        inv_taxable_amount = taxable_amount
        inv_tax_amount = tax_amt

        tot_taxbl_amt = taxable_amount
        tot_tax_amt = tax_amt
        inv_tot_amt = amt

        item_data.update({
            f"taxblAmt{tax_code}": flt(inv_taxable_amount, 4),
            f"taxAmt{tax_code}": flt(inv_tax_amount, 4),

            f"taxRt{tax_code}": tax_rate,

            "totTaxblAmt": flt(tot_taxbl_amt, 4),
            "totTaxAmt": flt(tot_tax_amt, 4),
            "totAmt": flt(inv_tot_amt, 4)
        })
    # elif item_doc.custom_industry_tax_type == "Rental Tax":
    #     not_supported()
    # elif item_doc.custom_industry_tax_type == "Service Tax":
    #     not_supported()
    else:
        tax_rate = (flt(tax_rate, 4)/100) + 1 if tax_rate else 0.0
        amt = flt(abs(amt), 4)
        
        taxable_amount = flt((amt/tax_rate) if tax_rate != 0 else 0, 4)
        tax_amt = flt(amt - taxable_amount, 4)
        
        item_taxes = {
            "totAmt": amt,
            "vatTaxblAmt": taxable_amount,
            "vatAmt": tax_amt
        }
        
        if tax_code in ["A", "B", "C1", "C2", "C3", "D", "E", "Rvat"]:    
            item_taxes.update({
                "vatCatCd": tax_code.upper(),
            })
        elif tax_code in ["Tot", "TOT"]:
            item_taxes.update({
                "vatCatCd": "A", #TODO: API failing to accept TOT, have to force a VAT tax
                "taxCatCd": "TOT",
                "taxblAmt": amt,
                "taxAmt": 0,
                "vatAmt": 0
            })
            item_taxes.pop("vatAmt", None)

        item_data.update(item_taxes)
        
        # update each tax item being calculated
        tax_amount = item_taxes.get("vatAmt", 0)
        taxable_amount = item_taxes.get("vatTaxblAmt", 0)
        total_taxable_amount = item_taxes.get("vatTaxblAmt", 0)
        total_tax_amount = item_taxes.get("vatAmt", 0)
        total_amount = item_taxes.get("totAmt", 0)

        stock_item_data.update({
            f"taxAmt{tax_code}": flt(tax_amount, 4),
            f"taxblAmt{tax_code}": flt(taxable_amount, 4),
            "taxblAmtTot": 0,
            "taxAmtTot": 0,
            "totTaxblAmt": flt(total_taxable_amount, 4),
            "totTaxAmt": flt(total_tax_amount, 4),
            "totAmt": flt(total_amount, 4)
        })
    stock_item_data.update({
        "sarTyCd": transaction_code,
        "itemList": [item_data]
    })
    stock_item_data.update(get_doc_user_data(ledger)) # add user info

    return stock_item_data


def create_stock_master_data(stock_items, invoice):

    stock_master_data = {
        "tpin": stock_items.get("tpin"),
        "bhfId": stock_items.get("bhfId"),
        "stockItemList": []
    }

    item_balances = get_item_balances()
    new_items = []

    if stock_items.get("itemList"):
        for item in stock_items.get("itemList"):
            item_code = item.get("itemCd")
            item_bal = item_balances.get(item_code, 0)

            # item_qty = flt(item.get("qty"))
            # if invoice.is_return == 1:

            balance = 0
            if item_bal > 0:
                balance = item_bal
            
            new_items.append({
                "itemCd": item_code,
                "rsdQty": balance
            })

    stock_master_data.update({"stockItemList": new_items})
    stock_master_data.update(get_doc_user_data(invoice)) # add user info
    return stock_master_data

def get_item_balances():
    item_balances = frappe.get_all("Bin", fields=["item_code", "actual_qty"], filters={"actual_qty": (">", 0)}, limit=0)
    return {d.item_code: flt(d.actual_qty) for d in item_balances}


def create_stock_item_data(invoice, invoice_data):
    posting_date_only = api_date_format(invoice.posting_date, date_only=True)

    stock_item_data = {
        "tpin": invoice_data.get("tpin"),
        "bhfId": invoice_data.get("bhfId"),
        "sarNo": invoice.custom_receipt_no, # TODO: get sar no from invoice
        "orgSarNo": 0,
        "regTyCd": "M",
        "custTpin": invoice_data.get("custTpin"),
        "custNm": invoice_data.get("custNm"),
        "custBhfId": invoice_data.get("bhfId"),
        "sarTyCd": "13" if invoice.is_return == 0 else "12",
        "ocrnDt": posting_date_only,
        "totItemCnt": len(invoice.items),
        "totTaxblAmt": invoice_data.get("totTaxblAmt"),
        "totTaxAmt": invoice_data.get("totTaxAmt"),
        "totAmt": invoice_data.get("totAmt"),
        "remark": invoice.remarks,
        "itemList": []
    }
    items = invoice_data.get("itemList")

    if items:
        for item in items:
            tax_code = item.get("vatCatCd", "A") # ISSUE: only VAT codes are supported
            taxable = item.get("vatTaxblAmt", 0.0)
            tax = item.get("vatAmt", 0.0)

            if tax_code in ["A", "B", "C1", "C2", "C3", "D", "E", "Rvat", "TOT"]:
                taxable = item.get("vatTaxblAmt", 0.0)
                tax = item.get("vatAmt", 0.0)

            item.update({
                    "vatCatCd": tax_code,
                    "taxblAmt": taxable,
                    "taxAmt": tax
            })

    stock_item_data.update({"itemList": items})
    stock_item_data.update(get_doc_user_data(invoice)) # add user info
    return stock_item_data


def get_payment_code(doc):
    if doc.doctype == "Purchase Invoice":
        if doc.is_paid and doc.mode_of_payment and doc.paid_amount > 0:
            return frappe.get_cached_value("Mode of Payment", doc.mode_of_payment, "custom_cd") or "02"
        else:
            return "02"

    else:
        if not doc.payments or doc.is_pos == 0:
            return "02"
        payment_amounts = [(d.name, d.amount, d.custom_payment_cd, d.mode_of_payment) for d in doc.payments if d.amount > 0]
        sorted_payment_amounts = sorted(payment_amounts, key=lambda x: x[1], reverse=True)
        
        if not sorted_payment_amounts:
            return "02"  # Default code if no payments
        
        highest_payment = sorted_payment_amounts[0]
        return highest_payment[2] if highest_payment[2] else frappe.get_cached_value("Mode of Payment", highest_payment[3], "custom_cd") or "02"

def get_cancel_date(name):
    try:
        doc = frappe.get_cached_doc("Sales Invoice", name)
        if doc:
            return api_date_format(f"{doc.posting_date} {doc.posting_time}")
    except Exception as e:
        return None


def get_country_from_address_display(address, countries):
    # Split the address by <br> or comma
    queries = {word.strip() for word in re.split(r'<br>|,', address) if word.strip()}
    
    # Create a case-insensitive dictionary for country lookup
    country_lookup = {d.lower(): d for d in countries}
    
    # Sort the set from end to start
    sorted_queries = sorted(queries)
    
    # Check if any of the sorted queries match a country name
    for q in sorted_queries:
        q_lower = q.lower()
        if q_lower in country_lookup:
            return country_lookup[q_lower]
    return None


def get_country_code(doc):
    country_code = "ZM"
    if doc.doctype == "Sales Invoice":
        if not doc.customer_address and not doc.shipping_address_name and not doc.dispatch_address_name and not doc.address_display:
            return country_code
        else:
            countries = {d.name: d.code for d in frappe.get_all("Country", fields=["name", "code"], limit=0)}
            if doc.customer_address or doc.address_display:
                if doc.customer_address:
                    country = frappe.get_cached_value("Address", doc.customer_address, "country")
                elif doc.address_display:
                    country = get_country_from_address_display(doc.address_display, countries)
                if country:
                    country_code = countries[country]

            elif doc.shipping_address_name:
                if doc.shipping_address_name:
                    country = frappe.get_cached_value("Address", doc.customer_address, "country")
                elif doc.address_display:
                    country = get_country_from_address_display(doc.address_display, countries)
                if country:
                    country_code = countries[country]

            elif doc.dispatch_address_name:
                if doc.dispatch_address_name:
                    country = frappe.get_cached_value("Address", doc.customer_address, "country")
                elif doc.address_display:
                    country = get_country_from_address_display(doc.address_display, countries)
                if country:
                    country_code = countries[country]
        return country_code.upper()
    else:
        if not doc.supplier_address and not doc.shipping_address and not doc.billing_address and not doc.address_display:
            return country_code
        else:
            countries = {d.name: d.code for d in frappe.get_all("Country", fields=["name", "code"], limit=0)}
            if doc.supplier_address or doc.address_display:
                if doc.supplier_address:
                    country = frappe.get_cached_value("Address", doc.supplier_address, "country")
                elif doc.address_display:
                    country = get_country_from_address_display(doc.address_display, countries)
                if country:
                    country_code = countries[country]

            elif doc.shipping_address:
                if doc.shipping_address:
                    country = frappe.get_cached_value("Address", doc.supplier_address, "country")
                elif doc.address_display:
                    country = get_country_from_address_display(doc.address_display, countries)
                if country:
                    country_code = countries[country]

            elif doc.billing_address:
                if doc.billing_address:
                    country = frappe.get_cached_value("Address", doc.billing_address, "country")
                elif doc.address_display:
                    country = get_country_from_address_display(doc.address_display, countries)
                if country:
                    country_code = countries[country]
        return country_code.upper()



def ensure_tax_accounts(codes, company_name, abbr):
    code_names = {d.cd: d for d in codes}

    tax_accounts = frappe.get_all("Account", 
                                filters={"account_type": "Tax", 
                                    "company": company_name, 
                                    "is_group": 0, 
                                    "parent_account": ("like", f"%Duties and Taxes - {abbr}")
                                }, 
                                fields=["account_name", "parent_account"], 
                                limit=0)
    tax_account_names = {d.account_name: d.parent_account for d in tax_accounts}
    for code_name in code_names:
        if code_name not in tax_account_names.keys():
            account = frappe.new_doc("Account")
            account.account_type = "Tax"
            account.company = company_name
            account.account_name = code_name
            account.tax_rate = code_names[code_name].user_dfn_cd1
            account.parent_account = tax_accounts[0].parent_account
            account.insert(ignore_permissions=True)

def create_item_taxes(company, tax_codes):
    abbr = company.abbr
    codes = frappe.get_all("Code", filters={"cd_cls": "04" }, fields=["name", "cd", "cd_nm", "cd_cls", "mapped_entry", "user_dfn_cd1"], limit=0)
    ensure_tax_accounts(codes, company.name, abbr)

    for tax_code in codes:
        if tax_code.cd not in tax_codes.keys():
            item_tax = frappe.new_doc("Item Tax Template")
            item_tax.title = tax_code.cd_nm
            item_tax.custom_smart_invoice_tax_code = tax_code.name
            item_tax.company = company.name
            
            # Create a child table row for taxes
            item_tax.append("taxes", {
                "tax_type": f"{tax_code.cd} - {abbr}",
                "tax_rate": flt(tax_code.user_dfn_cd1 or 0.0)
            })

            item_tax.flags.ignore_permissions = True
            item_tax.flags.ignore_mandatory = True
            
            item_tax.insert()

            if item_tax.name:

                title = f"{tax_code.cd_nm} - {abbr}"
                tax_codes[tax_code.cd] = title
    return tax_codes

@frappe.whitelist()
def set_item_taxes(invoice, auto_tax=None):
    """sets default Item Tax Template for invoice items if nothing is set
        called on save
    """

    if isinstance(invoice, str):
        invoice = frappe.get_doc("Sales Invoice", invoice)
    
    auto_tax = invoice.custom_automatically_set_item_taxes
    if auto_tax == 0:
        return
        
    item_tax_templates = frappe.get_all("Item Tax Template", filters={"company": invoice.company, "disabled": 0, "custom_code": ("is", "set")}, fields=["name", "custom_code"], limit=0)
    
    tax_templates_by_code = {d.custom_code: d.name for d in item_tax_templates}    
    company = frappe.get_cached_doc("Company", invoice.company)

    default_item_tax = tax_templates_by_code.get(company.custom_tax_code, None)

    if not default_item_tax:
        tax_templates_by_code = create_item_taxes(company, tax_templates_by_code)
    
    default_item_tax = tax_templates_by_code.get(company.custom_tax_code, None)
        
    for item in invoice.items:
        if item.item_tax_template:
            continue
        elif default_item_tax:
            item.item_tax_template = default_item_tax
    return invoice


def not_supported():
    frappe.throw("Smart Invoice does not support this feature/tax type yet. Please contact support.")


# def prepare_invoice_data(invoice, branch=None):
#     if isinstance(invoice, str):
#         invoice = frappe.get_cached_doc("Sales Invoice", invoice)
    
#     if invoice.discount_amount:
#         frappe.throw(_("Sorry, invoice level discounting is not yet supported in Smart Invoice. You can set item level discounts instead."), title="Not Supported")
    
#     company = frappe.get_cached_doc("Company", invoice.company)
#     if invoice.doctype == "Purchase Invoice":
#         party = frappe.get_cached_doc("Supplier", invoice.supplier)
#     else:
#         party = frappe.get_cached_doc("Customer", invoice.customer)
    
#     if not branch:
#         branches = get_user_branches()
#         branch = next((b for b in branches if b['custom_company'] == invoice.company), None)
#         if not branch and not frappe.flags.batch:
#             # TODO: use default branch from company if its a sync_job
#             frappe.throw("No branch found for the current user and company")
    
#     posting_date = invoice.posting_date
#     posting_time = invoice.posting_time or "00:00:00"

#     # Group variables that depend on is_return
#     if invoice.is_return == 1:
#         original_invoice = frappe.get_cached_doc("Sales Invoice", invoice.return_against)
#         rcpt_ty_cd = "R"
#         sales_stts_cd = "05"
#         org_invc_no = original_invoice.custom_receipt_no
#         org_sdc_id = original_invoice.custom_sdc_id
#         rfd_rsn_cd = invoice.custom_refund_reason_code
#         rfd_dt = None
#         if rfd_rsn_cd:
#             rfd_dt = api_date_format(f"{posting_date} {posting_time}")
#         cancel_date = get_cancel_date(invoice)
#     else:
#         rcpt_ty_cd = "S"
#         sales_stts_cd = "02"
#         org_sdc_id = None
#         org_invc_no = 0
#         rfd_dt = None
#         rfd_rsn_cd = ""
#         cancel_date = None
        
#     posting_date_time = api_date_format(f"{posting_date} {posting_time}")
#     posting_date_only = api_date_format(posting_date, date_only=True)

#     country_code = get_country_code(invoice)
#     invoice_name = api_date_format(f"{frappe.utils.get_datetime_str(frappe.utils.get_datetime())}")
    
#     data = {
#         "tpin": branch['custom_tpin'],
#         "bhfId": branch['custom_bhf_id'],        
#         "orgSdcId": org_sdc_id,
#         "orgInvcNo": org_invc_no,
#         "cisInvcNo": invoice_name,# invoice.name, # 
#         "custTpin": party.tax_id,
#         "custNm": party.customer_name,
#         "salesTyCd": "N",  # Assuming normal sale
#         "rcptTyCd": rcpt_ty_cd,
#         "pmtTyCd": get_payment_code(invoice),
#         "salesSttsCd": sales_stts_cd,
#         "cfmDt": posting_date_time,
#         "salesDt": posting_date_only,
#         "stockRlsDt": None if invoice.update_stock == 0 else posting_date_time,
#         "cnclReqDt": cancel_date,
#         "cnclDt": cancel_date,
#         "rfdDt": rfd_dt,
#         "rfdRsnCd": rfd_rsn_cd,
#         "totItemCnt": len(invoice.items),
#         "prchrAcptcYn": "Y",
#         "remark": invoice.remarks or "",
#         "saleCtyCd": "1",
#         "lpoNumber": None, # invoice.po_no or None,
#         "destnCountryCd": country_code if not "ZM" else None,
#         "currencyTyCd": invoice.currency or "XXX",
#         "exchangeRt": invoice.conversion_rate,
#         "dbtRsnCd": None,
#         "invcAdjustReason": None,
#         "cashDcAmt": flt(invoice.discount_amount, 3),
#         "cashDcRt": flt(invoice.additional_discount_percentage, 3),

#         "taxRtA": 16,
#         "taxblAmtA": 0.0,
#         "taxAmtA": 0.0,
#         "taxRtB": 16,
#         "taxblAmtB": 0.0,
#         "taxAmtB": 0.0,
#         "taxRtC1": 0,
#         "taxblAmtC1": 0.0,
#         "taxAmtC1": 0.0,
#         "taxRtC2": 0,
#         "taxblAmtC2": 0.0,
#         "taxAmtC2": 0.0,
#         "taxRtC3": 0,
#         "taxblAmtC3": 0.0,
#         "taxAmtC3": 0.0,
#         "taxRtD": 0,
#         "taxblAmtD": 0.0,
#         "taxAmtD": 0.0,
#         "taxRtRvat": 0,
#         "taxblAmtRvat": 0.0,
#         "taxAmtRvat": 0.0,
#         "taxRtE": 0,
#         "taxblAmtE": 0.0,
#         "taxAmtE": 0.0,
#         "taxRtF": 10,
#         "taxblAmtF": 0.0,
#         "taxAmtF": 0.0,
#         "taxRtTot": 0,
#         "taxblAmtTot": 0.0,
#         "taxAmtTot": 0.0,

#         "taxRtIpl1": 5,
#         "taxblAmtIpl1": 0.0,
#         "taxAmtIpl1": 0.0,
#         "taxRtIpl2": 0,
#         "taxblAmtIpl2": 0.0,
#         "taxAmtIpl2": 0.0,
#         "taxRtTl": 1.5,
#         "taxblAmtTl": 0.0,
#         "taxAmtTl": 0.0,
#         "taxRtEcm": 5,
#         "taxblAmtEcm": 0.0,
#         "taxAmtEcm": 0.0,
#         "taxRtExeeg": 3,
#         "taxblAmtExeeg": 0.0,
#         "taxAmtExeeg": 0.0,

#         "tlAmt": 0.0,
#         "totTaxblAmt": 0.0,
#         "totTaxAmt": 0.0,
#         "totAmt": 0.0,
#         "itemList": []
#     }
#     items = []
#     data, items = calculate_item_taxes(company, invoice, data, items)

#     data.update({"itemList": items})
#     data.update(get_doc_user_data(invoice)) # add user info

#     return data


# def calculate_item_taxes(company, invoice, data, items):
#     items = []

#     for idx, item in enumerate(invoice.items, start=1):

#         item_doc = frappe.get_cached_doc("Item", item.item_code)
#         unit_cd, pkg_unit = get_unit_code(item_doc, invoice.company)
        
#         item_data = {
#             "itemSeq": idx,
#             "itemCd": item.item_code,
#             "itemClsCd": item_doc.custom_item_cls_cd or company.custom_default_item_class,
#             "itemNm": item.item_code,
#             "bcd": None,
#             "pkgUnitCd": pkg_unit or "PACK",
#             "pkg": flt(abs(item.qty), 3),
#             "qtyUnitCd": unit_cd or "U",
#             "qty": flt(abs(item.qty), 3),
#             "prc": flt(item.rate, 3),
#             "splyAmt": flt(abs(item.amount), 3),
#             "dcRt": 0.0, # flt(item.discount_percentage, 3) if item.discount_percentage else 0.0,
#             "dcAmt": 0.0, # flt(item.discount_amount, 3) if item.discount_amount else 0.0,
#             "isrccCd": None,
#             "isrccNm": None,
#             "rrp": flt(item.rate, 3),
#             "isrcRt": 0.0,
#             "isrcAmt": 0.0,
#             "totDcAmt": 0.0,
#             "totAmt": flt(abs(item.amount), 3),
#             "vatTaxblAmt": 0.0,
#             "vatAmt": 0.0
#         }

#         # set tax defaults
#         code_doc = None        
#         if not item_doc.custom_industry_tax_type or not item.item_tax_template or not item.custom_tax_rate or not item.custom_tax_code:
#             if not item.custom_tax_code:
#                 item.custom_tax_code = company.custom_tax_code
#                 if not item.custom_tax_code:
#                     frappe.throw(f"Set <strong>Tax Bracket</strong> in company <a href='{company.get_url()}'>{frappe.bold(invoice.company)}</a>")

#             if not item.item_tax_template or not item.custom_tax_rate:
#                 if item.custom_tax_code:
#                     code_doc = frappe.get_cached_value("Code", {"cd": item.custom_tax_code}, ["name", "cd_nm", "user_dfn_cd1"], as_dict=True)
#                 else:
#                     code_doc = frappe.get_cached_doc("Code", company.custom_tax_bracket)

#                 item.custom_tax_rate  = flt(code_doc.user_dfn_cd1, 2)
#                 item.item_tax_template = f"{code_doc.cd_nm} - {company.abbr}"           
            
#             # do industry tax type helps choose the correct calculation
#             if not item_doc.custom_industry_tax_type:
#                 templates = {
#                     f"TOT - {company.abbr}": "TOT",
#                     f"Standard Rated(16%) - {company.abbr}": "VAT",
#                     f"Minimum Taxable Value (MTV-16%) - {company.abbr}": "VAT",
#                     f"Reverse VAT - {company.abbr}": "VAT",
#                     f"Disbursement - {company.abbr}": "Zero Rated (VAT)",
#                     f"Exempt - {company.abbr}": "Zero Rated (VAT)",
#                     f"Zero-rated by nature - {company.abbr}": "Zero Rated (VAT)",
#                     f"Zero-rated LPO - {company.abbr}": "Zero Rated (VAT)",
#                     f"Exports(0%) - {company.abbr}": "Zero Rated (VAT)",
#                     f"Excise Electricity - {company.abbr}": "Excise Duty",
#                     f"Excise on Coal - {company.abbr}": "Excise Duty",
#                     f"Tourism Levy - {company.abbr}": "Tourism Levy",
#                     f"Insurance Premium Levy - {company.abbr}": "Insurance Premium Levy",
#                     f"Re-insurance - {company.abbr}": "Insurance Premium Levy"
#                 }
#                 # defaults to VAT if no industry tax type is set, VAT will work for VAT and TOT depending on the computed item tax code
#                 item_doc.custom_industry_tax_type = templates.get(item.item_tax_template, "VAT")


#             if item.idx == 1:
#                 frappe.msgprint("Item Taxes not set. Using company default.", indicator="Warning", alert=True)

#         tax_code = item.custom_tax_code.title()

#         # Calculate taxes for the item
#         if item_doc.custom_industry_tax_type in ["Excise Duty", "Tourism Levy", "Insurance Premium Levy"]:
#             tax_types = {
#                 "Excise Duty": "excise",
#                 "Tourism Levy": "tl",
#                 "Insurance Premium Levy": "ipl"
#             }

#             tax_rate = flt(item.custom_tax_rate)

#             amt = flt(abs(item.amount), 4)
#             rate = 0.0
#             taxable_amount = 0.0
#             tax_amt = 0.0
            
#             if tax_rate != 0:
#                 rate = (flt(tax_rate/100) + 1)
#                 taxable_amount = flt(amt/rate, 4)
#                 tax_amt = flt(amt - taxable_amount, 4)

#             tax_type = tax_types[item_doc.custom_industry_tax_type]

#             if item_doc.custom_industry_tax_type in ["Tourism Levy", "Insurance Premium Levy"]:
#                 if tax_code == "Ipl2":
#                     taxable_amount = amt

#                 item_data.update({
#                     f"{tax_type}CatCd": item.custom_tax_code,
#                     f"{tax_type}TaxblAmt": taxable_amount,
#                     f"{tax_type}Amt": tax_amt
#                 })
#             elif item_doc.custom_industry_tax_type == "Excise Duty":
#                 item_data.update({
#                     f"{tax_type}TxCatCd": item.custom_tax_code,
#                     f"{tax_type}TaxblAmt": taxable_amount,
#                     f"{tax_type}TxAmt": tax_amt
#                 })

#             inv_taxable_amount = data[f"taxblAmt{tax_code}"] + taxable_amount
#             inv_tax_amount = data[f"taxAmt{tax_code}"] + tax_amt

#             tot_taxbl_amt = data[f"totTaxblAmt"] + taxable_amount
#             tot_tax_amt = data[f"totTaxAmt"] + tax_amt
#             inv_tot_amt = data["totAmt"] + amt

#             data.update({
#                 f"taxblAmt{tax_code}": flt(inv_taxable_amount, 4),
#                 f"taxAmt{tax_code}": flt(inv_tax_amount, 4),

#                 f"taxRt{tax_code}": tax_rate,

#                 "totTaxblAmt": flt(tot_taxbl_amt, 4),
#                 "totTaxAmt": flt(tot_tax_amt, 4),
#                 "totAmt": flt(inv_tot_amt, 4)
#             })
#         elif item_doc.custom_industry_tax_type == "Rental Tax":
#             not_supported()
#         elif item_doc.custom_industry_tax_type == "Service Tax":
#             not_supported()
#         else:
#             item_taxes = {}
#             tax_rate = (flt(item.custom_tax_rate, 4)/100) + 1 if item.custom_tax_rate else 0.0
#             amt = flt(abs(item.amount), 4)
            
#             taxable_amount = flt((amt/tax_rate) if tax_rate != 0 else 0, 4)
#             tax_amt = flt(amt - taxable_amount, 4)
            
#             item_taxes = {
#                 "totAmt": amt,
#                 "vatTaxblAmt": taxable_amount,
#                 "vatAmt": tax_amt
#             }
            
#             if tax_code in ["A", "B", "C1", "C2", "C3", "D", "E", "Rvat"]:    
#                 item_taxes.update({
#                     "vatCatCd": tax_code.upper(),
#                 })
#             elif tax_code == "Tot":
#                 item_taxes.update({
#                     "taxCatCd": tax_code.upper(),
#                     "vatTaxblAmt": amt,
#                     "vatAmt": 0
#                 })

#             item_data.update(item_taxes)
            
#             # total main doc from each item
#             tax_amount = data[f"taxAmt{tax_code}"] + item_taxes.get("vatAmt", 0)
#             taxable_amount = data[f"taxblAmt{tax_code}"] + item_taxes.get("vatTaxblAmt", 0)
#             total_taxable_amount = data[f"totTaxblAmt"] + item_taxes.get("vatTaxblAmt", 0)
#             total_tax_amount = data[f"totTaxAmt"] + item_taxes.get("vatAmt", 0)
#             total_amount = data["totAmt"] + item_taxes.get("totAmt", 0)

#             data.update({
#                 f"taxAmt{tax_code}": flt(tax_amount, 4),
#                 f"taxblAmt{tax_code}": flt(taxable_amount, 4),
#                 "taxblAmtTot": 0,
#                 "taxAmtTot": 0,
#                 "totTaxblAmt": flt(total_taxable_amount, 4),
#                 "totTaxAmt": flt(total_tax_amount, 4),
#                 "totAmt": flt(total_amount, 4)
#             })
#         items.append(item_data)
#     return data, items


def get_item_taxes(item, tax_code):
    """Calculate tax amounts and return tax data dictionary for an item

    This function calculates VAT/tax amounts for an item based on its tax rate and amount.
    It handles both VAT tax codes (A,B,C1,C2,C3,D,RVAT) and TOT tax code differently.

    Args:
        item: Item document containing tax rate and amount
        tax_code: Tax category code (e.g. "A", "B", "TOT" etc)

    Returns:
        dict: Dictionary containing:
            - totAmt: Total amount including tax
            - vatTaxblAmt: VAT taxable amount 
            - vatAmt: VAT tax amount
            - vatCatCd: VAT category code (for VAT tax codes)
            - taxCatCd: Tax category code (for TOT)
    """

    tax_rate = (flt(item.custom_tax_rate, 4)/100) + 1 if item.custom_tax_rate else 0.0 # v2: use system default
    amt = flt(abs(item.amount), 4)
    
    taxable_amount = flt((amt/tax_rate) if tax_rate != 0 else 0, 4)
    tax_amt = flt(amt - taxable_amount, 4)
    
    taxes = {
        "totAmt": amt,
        "vatTaxblAmt": taxable_amount,
        "vatAmt": tax_amt
    }
    if tax_code in ["A", "B", "C1", "C2", "C3", "D", "E", "Rvat"]:    
        taxes.update({
            "vatCatCd": tax_code.upper(),
        })
    elif tax_code == "TOT":
        taxes.update({
            "taxCatCd": tax_code.upper(),
            "vatTaxblAmt": amt,
            "vatAmt": 0
        })

    return taxes


def prepare_tax_data(invoice): # TODO: Remove - deprecated
    
    taxes = {}
    taxable_amounts = {
        "Rvat": {"taxblAmtRvat": flt(invoice.net_total, 3)},
        "E": {"taxblAmtE": flt(invoice.net_total, 3)},
        "F": {"taxblAmtF": flt(invoice.net_total, 3)},
        "Ipl1": {"taxblAmtIpl1": flt(invoice.net_total, 3)},
        "Ipl2": {"taxblAmtIpl2": flt(invoice.net_total, 3)},
        "Tl": {"taxblAmtTl": flt(invoice.net_total, 3)},
        "Ecm": {"taxblAmtEcm": flt(invoice.net_total, 3)},
        "Exeeg": {"taxblAmtExeeg": flt(invoice.net_total, 3)},
    }
    tax_amounts = {
        "Rvat": {"taxAmtRvat": flt(invoice.net_total, 3)},
        "E": {"taxAmtE": 0.0},
        "F": {"taxAmtF": 0.0},
        "Ipl1": {"taxAmtIpl1": 0.0},
        "Ipl2": {"taxAmtIpl2": 0.0},
        "Tl": {"taxAmtTl": 0.0},
        "Ecm": {"taxAmtEcm": 0.0},
        "Exeeg": {"taxAmtExeeg": 0.0},
    }
    tax_rates = {
        "A": {"taxRtA": 16},
        "B": {"taxRtB": 16},
        "C1": {"taxRtC1": 0},
        "C2": {"taxRtC2": 0},
        "C3": {"taxRtC3": 0},
        "D": {"taxRtD": 0},
        "Rvat": {"taxRtRvat": 16},
        "E": {"taxRtE": 0},
        "F": {"taxRtF": 10},
        "Ipl1": {"taxRtIpl1": 5},
        "Ipl2": {"taxRtIpl2": 0},
        "Tl": {"taxRtTl": 1.5},
        "Ecm": {"taxRtEcm": 5},
        "Exeeg": {"taxRtExeeg": 3},
    }

    return taxes

def get_doc_user_data(doc):
    owner_name = frappe.get_cached_value('User', doc.owner, 'full_name')
    return {
        "regrId": doc.owner,
        "regrNm": owner_name,
        "modrId": frappe.session.user,
        "modrNm": owner_name if frappe.session.user == doc.owner else frappe.get_cached_value('User', frappe.session.user, 'full_name')
    }

@frappe.whitelist()
def get_user_branch(name, user=frappe.session.user):
    join = ''
    more_conditions = ''

    if user != "Administrator":
        more_conditions = f'AND u.user_id = "{user}"AND u.user_id = "{user}"'
        join = 'RIGHT JOIN `tabBranch User` as u ON b.name = u.parent'

    sql = f"""
        SELECT b.branch, b.custom_bhf_id, b.custom_tpin, b.custom_company
        FROM `tabBranch` as b
        {join}
        WHERE 
            (b.name = "{name}" OR
            LOWER(b.name) = "{name.lower()}") 
            {more_conditions}
    """

    return frappe.db.sql(sql, as_dict=1)

@frappe.whitelist()
def get_user_branches(name=None, user=None):
    if name:
        branch = get_user_branch(name, user)
        if branch:
            return branch

    branches = frappe.get_all("Branch", fields=["branch", "custom_bhf_id", "custom_tpin", "custom_company"], filters={"custom_bhf_id": ["is", "set"]}, limit=0)
    branch_users = frappe.get_all("Branch User", fields=["*"], filters={"user_id": ("in", [frappe.session.user])}, limit=0)

    branch_data = []
    for branch in branches:
        for bu in branch_users:
            branch_data.append({
                "branch": branch.branch,
                "custom_bhf_id": branch.custom_bhf_id,
                "custom_tpin": branch.custom_tpin,
                "user_id": bu.user_id,
                "custom_company": branch.custom_company
            })
        branch_data.append({
            "branch": branch.branch,
            "custom_bhf_id": branch.custom_bhf_id,
            "custom_tpin": branch.custom_tpin,
            "user_id": "Administrator",
            "custom_company": branch.custom_company
        })
    if not branch_data:
        branch_data = [{
            "branch": "Headquarter",
            "custom_bhf_id": "000",
            "custom_tpin": None,
            "user_id": None
        }]
    return branch_data


def is_migration():
    stack = inspect.stack()
    b = any(
        frame.function == 'migrate' or
        'install' in frame.function
        
               for frame in stack)
    if b:
        print('Skipping action during installation/migration')
    return b
    

def get_unit_code(item, company):
    """
    - search codes for matching UOM
    - use fallback UOMs if nothting is found
        - smart_invoice_settings.default_uom : suggest each
        - smart_invoice_settings.default_pkg_uom : suggest pack
    """

    unit_cd = None
    pkg_unit = None
    if item.custom_qty_unit_cd:
        unit_cd =  item.custom_qty_unit_cd
    if item.custom_pkg_unit_cd:
        pkg_unit =  item.custom_pkg_unit_cd

    if not unit_cd or not pkg_unit:

        codes = frappe.get_all("Code", fields=["name", "cd", "cd_nm", "cd_cls"], filters={"cd_cls": ["in", ["10", "17"]]})

        for code in codes:
            if (code.cd_nm.lower() == item.stock_uom.lower() or 
                    item.stock_uom.lower() == code.cd_nm.lower() or 
                    code.cd_nm.lower() == item.stock_uom.lower()):
                unit_cd = code.cd
            if item.custom_pkg_unit:
                if (code.cd_nm.lower() == item.custom_pkg_unit.lower() or 
                        item.custom_pkg_unit.lower() == code.cd_nm.lower() or 
                        code.cd_nm.lower() == item.custom_pkg_unit.lower()):
                    pkg_unit = code.cd
    
    defaults = []
    company_doc = None
    if not unit_cd:
        company_doc = frappe.get_cached_doc("Company", company)
        unit_cd = company_doc.custom_unit_code
        defaults.append(company_doc.custom_unit_code)
    if not pkg_unit:
        if not company_doc:
            company_doc = frappe.get_cached_doc("Company", company)
        pkg_unit = company_doc.custom_packaging_unit_code
        defaults.append(company_doc.custom_packaging_unit_code)
    
    if defaults and not frappe.flags.skip_failing:
        frappe.msgprint(f"Using default unit codes: {', '.join(defaults)} for Item {item.item_code}", indicator='Warning', alert=True)

    return unit_cd, pkg_unit


@frappe.whitelist()
def create_codes_if_needed(item=None):
    count = frappe.get_all("Code", limit=0)    
    if len(count) < 100:
        update_codes(initialize=True)
        frappe.msgprint("Updated UOM and Packaging Unit codes", indicator='green', alert=True)


def get_item_price(item_code, company, price_list="Standard Selling", customer_group="All Customer Groups", qty=1, party=None):
    from erpnext.utilities.product import get_price
    price = get_price(item_code, price_list, customer_group, company, qty=1, party=None)
    return price.price_list_rate if price else 0


@frappe.whitelist()
def update_item_api(item, method=None, branch=None):
    if not item:
        return

    if type(item) == str:
        item = frappe.get_cached_doc("Item", item)
    data = prepare_item_data(item, branch=branch)

    item_data = []
    for item in data:
        response_doc = api("/api/method/smart_invoice_api.api.update_item", item)
        response = response_doc.get('response', None)
        item_data.append(validate_api_response(response_doc))

        try:
            reponse_json = json.loads(response)
            if reponse_json.get('resultCd') not in ["000", "001"]:
                if reponse_json.get('resultCd') == "999":
                    frappe.msgprint(title=f"Smart Invoice Error - {reponse_json.get('resultCd')}", msg="Try using setting Item Class to <strong>Unclassified Product</strong>")
                else:
                    frappe.msgprint(title="Smart Invoice Error", msg=reponse_json.get('msg'))
        except Exception as e:
            frappe.msgprint(title="Smart Invoice Error", msg=str(e))

    return item_data

def get_items_api(initialize=False):    
    data = {}
    if initialize:
        data.update({"initialize": True})

    response = api("/api/method/smart_invoice_api.api.select_items", data)
    return validate_api_response(response)


def get_item_api(item_code):    
    data = {
        "itemCd": item_code
    }
    response = api("/api/method/smart_invoice_api.api.select_item", data)
    return validate_api_response(response)


@frappe.whitelist()
def generate_item_code(item, initialize=False):
    """
    Generate a custom item code based on the following format:
    ZM: Country of Origin (Zambia)
    2: Product Type (Finished Product)
    NT: Packaging Unit (NET)
    BA: Quantity Unity (Barrel)
    0000001: increments from 0000001 to N value (7 digits)
    """

    def get_next_value(doctype, field, padding=7):
        """
        Generate the next value for the given prefix, doctype, and field.
        """
        count = frappe.db.count(doctype, filters={field: ["!=", ""]})
        next_value = count + 1
        return str(next_value).zfill(padding)

    if(type(item) == str):
        item = frappe._dict(json.loads(item))

    if item.custom_generated_item_code:
        return item.custom_generated_item_code

    # Get the country code from the item's country of origin
    country_code = frappe.get_cached_value("Country", item.country_of_origin, "code").upper()

    # Get the product type code from the item's item group
    item_group = frappe.get_cached_doc("Item Group", item.item_group)
    product_type_code = item_group.custom_item_ty_cd or "2"  # Default to "2" for finished product

    # Get the packaging unit code and quantity unity code
    company_name = frappe.defaults.get_user_default("Company")
    unit, pkg_unit = get_unit_code(item, company_name)

    # Generate the next value for the item code
    item_code_seed = f"{country_code}{product_type_code}{pkg_unit}{unit}"
    next_val = get_next_value(doctype="Item", field="custom_generated_item_code", padding=7)

    return f"{item_code_seed}{next_val}"


@frappe.whitelist()
def sync_items(initialize=False):
    r = get_items_api(initialize=True)
    if not r:
        frappe.throw(title="Smart Invoice Error", msg="No data received, try again")
    if r.get("resultCd") != "000": 
        return
    
    data = r['data']['itemList']
    
    # Use itemNm as a fallback if itemCd is None
    si_items = {d.get("itemNm") or d for d in data}

    # Get local items for comparison
    local_items = set(frappe.get_all("Item", pluck="name", filters={"disabled": 0}, limit=0))

    # Compare Smart Invoice items with local items
    # missing_in_local = si_items - local_items
    missing_in_si = local_items - si_items
    # Calculate items present in both Smart Invoice and local system
    items_in_both = si_items.intersection(local_items)
    
    count = 0
    failed = 0
    failed_items = []
    item = None
    frappe.flags.skip_failing = True

    if initialize:
        # update items already in smart invoice
        for item in items_in_both:
            try:
                if update_item_api(item):
                    count += 1
                else:
                    failed += 1
                    failed_items.append(item)
            except frappe.exceptions.ValidationError as e:
                continue

    # create items not in smart invoice
    for item in missing_in_si:
        try:
            save_result = save_item_api(item)
            if save_result:
                count += 1
            else:
                failed += 1
                failed_items.append(item)
        except frappe.exceptions.ValidationError as e:
            continue
    
    frappe.flags.skip_failing = False
    if failed != 0:
        frappe.msgprint(f"{failed} items failed to sync to Smart Invoice due to missing data", indicator='red', alert=True)
        frappe.msgprint(f"<p>Failed items: {', '.join([f'<strong>{item}</strong>' for item in failed_items])}.</p><hr/> " +
            "<p>Check the following fields for each item: <ul><li>UOM</li><li>Package UOM</li><li>Item Type (in Item Group)</li></ul></p>", title="Smart Invoice Error - Missing Data", indicator='red')
    else:
        frappe.msgprint(f"{count} items synched to Smart Invoice", indicator='green', alert=True)
    return True
        

def prepare_item_data(item, branch=None):

    branches = []
    if branch:
        branches = [branch]
    else:
        branches = get_user_branches()

    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    
    tax_code = item.taxes[0].tax_category if item.taxes else None
    batch = None # skipping batch for now
    barcode = item.barcodes[0].barcode if item.barcodes else None
    item_type = frappe.get_cached_value("Item Group", item.item_group, "custom_item_ty_cd")

    if not item_type:
        if frappe.flags.skip_failing:
            item_type = "2"
        else:
            frappe.throw("Smart Invoice requires an Item Type for <strong>Item Group {0}</strong>.".format(frappe.bold(item.item_group)))

    item_data = []
    # check if item has a unit_code
    if item.custom_qty_unit_cd and item.custom_pkg_unit_cd:
        unit = item.custom_qty_unit_cd
        pkg_unit = item.custom_pkg_unit_cd
    elif not item.stock_uom or not item.custom_pkg_unit:
        unit, pkg_unit = get_unit_code(item, branches[0].get("custom_company"))
    
    for branch in branches:    
        if not branch.get("custom_bhf_id") != "001":
            continue    
        default_price = get_item_price(item.item_code, branch.get("custom_company"))
        unit, pkg_unit = get_unit_code(item, branch.get("custom_company"))
        gen_item_code = item.custom_generated_item_code or generate_item_code(item)
        if not item.custom_generated_item_code:
            frappe.db.set_value("Item", item.name, "custom_generated_item_code", gen_item_code)

        data = {        
            "tpin": branch.get("custom_tpin"),
            "bhfId": branch.get("custom_bhf_id"),
            "useYn": "Y" if item.disabled == 0 else "N",
            "itemCd": gen_item_code,
            "itemNm": item.item_code,
            "itemStdNm": item.item_name,
            "itemClsCd": item.custom_item_cls_cd,
            "itemTyCd": item_type,
            "orgnNatCd": frappe.get_cached_value("Country", item.country_of_origin, "code").upper(),
            "pkgUnitCd": pkg_unit,
            "qtyUnitCd": unit,
            "vatCatCd": tax_code,
            "iplCatCd": item.custom_ipl_cat_cd if item.custom_industry_tax_type == "Insurance Premium Levy" else None,
            "tlCatCd": item.custom_tl_cat_cd if item.custom_industry_tax_type == "Tourism Levy" else None,
            "exciseTxCatCd": item.custom_excise_code if item.custom_industry_tax_type == "Excise Duty" else None,
            "svcChargeYn": "Y" if item.custom_industry_tax_type == "Service Tax" else "N", # v2
            "rentalYn": "Y" if item.custom_industry_tax_type == "Rental Tax" else "N", # v2
            "btchNo": batch,
            "bcd": barcode,
            "dftPrc": default_price,
            "manufacturerTpin": item.custom_manufacturer_tpin,
            "manufactureritemCd": item.custom_manufacture_item_cd,
            "rrp": default_price,
            "isrcAplcbYn": "Y" if item.custom_industry_tax_type == "Insurance Premium Levy" else "N",
            "addInfo":item.description,
            "sftyQty": item.safety_stock,
            "useYn": "Y" if item.disabled == 0 else "N",        
            "regrNm": users[item.owner].full_name,
            "regrId": item.owner,
            "modrNm": users[frappe.session.user].full_name,
            "modrId": frappe.session.user
        }
        item_data.append(data)
    return item_data

@frappe.whitelist()
def save_item_api(item, method=None, branch=None):
    if not item:
        return

    if type(item) == str:
        item = frappe.get_cached_doc("Item", item)
    data = prepare_item_data(item, branch=branch)
    if not data:
        return False

    item_data = []
    for item in data:
        response_doc = api("/api/method/smart_invoice_api.api.save_item", item)
        response = response_doc.get('response', None)
        item_data.append(validate_api_response(response_doc))

        try:
            reponse_json = json.loads(response)
            if reponse_json.get('resultCd') not in ["000", "001"]:
                if reponse_json.get('resultCd') == "999":
                    frappe.throw(title=f"Smart Invoice Error - {reponse_json.get('resultCd')}", msg="Try using setting Item Class to <strong>Unclassified Product</strong>")
                else:
                    frappe.msgprint(title="Smart Invoice Error", msg=reponse_json.get('msg'))
        except Exception as e:
            frappe.msgprint(title="Smart Invoice Error", msg=str(e))
        
    return item_data


@frappe.whitelist()
def sync_customer(doc, method=None):
    frappe.db.commit()
    customer = doc.as_dict()

    if not customer.tax_id or len(customer.tax_id) != 10:
        frappe.throw(f"Smart Invoice requires 10 digit TPIN for {frappe.bold(customer.get('customer_name'))}. {frappe.bold(customer.get('tax_id'))} is not valid.")
    
    phone = customer.get("mobile_no") or None
    email = customer.get("email_id") or None
    fax = None
    address = None

    # Check if addr_list is in __onload
    if '__onload' in customer and 'addr_list' in customer['__onload']:
        for addr in customer['__onload']['addr_list']:
            if not address:
                address = ', '.join(filter(None, [addr.get("address_line1"), addr.get("address_line2"), addr.get("city"), addr.get("country")]))
            else:
                break
    if not address:
        if primary_address := customer.get('primary_address'):
            cleaned_address = primary_address.replace('<br>', '').replace('\n', ' ')  # Remove <br> and newlines
            address = ', '.join(filter(None, cleaned_address.split()))  # Split, filter empty parts, and join with commas
            
        if not address:
            frappe.throw(f"Smart Invoice requires an address for customers. Add an address for {frappe.bold(customer.get('customer_name'))}")
    
    # Check if contact_list is in __onload
    if '__onload' in customer and 'contact_list' in customer['__onload']:
        for contact in customer['__onload']['contact_list']:
            _phone = contact.get("mobile_no")
            _email = contact.get("email_id")
            _fax = contact.get("custom_fax_no")
            _address = contact.get("address")
            if not phone and _phone and _phone != '':
                phone = _phone
            if not email and _email and _email != '':
                email = _email
            if not fax and _fax and _fax != '':
                fax = _fax
            if not address and _address and _address != '':
                address = _address

    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    if not phone:
        frappe.throw(f"Smart Invoice requires a phone number for customers. Add a phone number for {frappe.bold(customer.get('customer_name'))}")

    data = {
        "tpin": customer.get("custom_tpin"),
        "bhfId": "000",
        "custNo": phone,
        "custTpin": customer.get("tax_id", ""),
        "custNm": customer.get("customer_name", ""),
        "adrs": address,
        "email": email,
        "faxNo": fax,
        "useYn": "Y",
        "remark": "",
        "regrNm": users[customer.get("owner")].full_name,
        "regrId": customer.get("owner", ""),
        "modrNm": users[frappe.session.user].full_name,
        "modrId": frappe.session.user
    }

    response = api("/api/method/smart_invoice_api.api.save_branche_customer", data)

    response = json.loads(response.get('response', None))

    if response:
        code = response.get("resultCd")
        msg = response.get("resultMsg")

        if code == "000": 
            frappe.msgprint(f"Synchronized customer details with Smart Invoice", indicator='green', alert=True)
        else:
            
            if code == "910":
                if "custNo" in msg:
                    frappe.msgprint(
                        title=f"Smart Invoice Error - {response.get('resultCd')}",
                        msg="The phone number length is incorrect, make sure its 10 digits"
                    )
                elif "TPIN" in msg:
                    frappe.throw(
                        title=f"Smart Invoice Error - {response.get('resultCd')}",
                        msg="TPIN is invalid, check if the length is correct"
                    )
                else:
                    frappe.msgprint(
                        title=f"Smart Invoice Error - {response.get('resultCd')}",
                        msg=str(response.get('resultMsg'))
                    )
    else:
        frappe.msgprint(f"Smart Invoice connection failure, please try again shortly.", indicator='red')
        return False


    return True


@frappe.whitelist()
def get_customer_api(customer, branch="Headquarter"):  # incomplete
    customer = validate_customer(customer)
    frappe.throw(f"Function is incomplete")

    if not customer:
        return
    data = {
        "tpin": customer.get("custom_tpin"),
        "bhfId": "000",
        "custmTpin": customer.tax_id
    }
    
    response = api("/api/method/smart_invoice_api.api.select_customer", data)
    return validate_api_response(response)


def get_branch_tpin(branch):
    if type(branch) == str:
        branch = frappe.get_cached_doc("Branch", branch)
        tpin = branch.custom_tpin
    else:
        tpin = branch.custom_tpin
    
    return tpin

    # if company:
    #     custom_tpin = company.tax_id
    # else: 
    #     settings = get_settings()
    #     custom_tpin = settings.tpin


@frappe.whitelist()
def save_customer_api(customer, company=None, branch=None):

    if not customer:
        return
    
    custom_bhf_id = branch.custom_bhf_id if branch else "000"
    tpin = get_branch_tpin(branch)

    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    address = customer.address_html
    contact = frappe.get_cached_doc("Contact", customer.contact_person)
    mobile_no = customer.mobile_no
    email = customer.email_id

    data={
        "tpin": tpin,
        "bhfId": custom_bhf_id,
        "custTpin": customer.tax_id,
        "custNo": mobile_no,
        "custNm": customer.customer_name,
        "email": email,
        "faxNo": contact.custom_fax_no,
        "adrs": address,
        "useYn": "Y",
        "regrNm": users[customer.owner].full_name,
        "regrId": customer.owner,
        "modrNm": users[frappe.session.user].full_name,
        "modrId": frappe.session.user
    }
    response = api("/api/method/smart_invoice_api.api.save_branche_customer", data)
    return validate_api_response(response)


def update_user_api(branch, user, use_yn):
    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    data = {
        "tpin": branch.custom_tpin,
        "bhfId": branch.custom_bhf_id,
        "userId": user.get("user_id"),
        "userNm": user.get("user_name"),
        "adrs": user.get("adrs"),
        "useYn": use_yn,
        "regrNm": users[branch.owner].full_name,
        "regrId": branch.owner,
        "modrNm": users[frappe.session.user].full_name,
        "modrId": frappe.session.user
        }

    response = api("/api/method/smart_invoice_api.api.save_branche_user", data)
    validate_api_response(response)
    return json.loads(response.get('response'))


@frappe.whitelist()
def update_api_users(branch):

    doc = frappe.get_cached_doc("Branch", branch)
    user_list = [user.user_id for user in doc.custom_branch_users]

    user_string = ", ".join(user_list)

    # checks if users where added or removed
    if (user_string == doc.custom_previous_branch_users):
        return
    
    
    user_changes = get_user_changes(doc, user_list)

    for user in user_changes:
        if user.get("change_type") == "added":
            # Enable user in the API
            update = update_user_api(doc, user, "Y")
        elif user.get("change_type") == "removed":
            # Disable user in the API
            update = update_user_api(doc, user, "N")

        print(update)
        if update.get("resultCd") not in ("000", "001", "801", "802", "803", "804", "805"):
            frappe.msgprint(f"Failed to {user.get('change_type')} {user.get('user_name')} on Smart Invoice", indicator='red', alert=True)
        else:
            frappe.msgprint(f"{user.get('change_type').title()} {user.get('user_name')} on Smart Invoice", indicator='green', alert=True)
        
    return user_string

def get_user_changes(doc, user_list):

    # Fetch all users' information
    all_users = {u.name: {
        "user_name": u.full_name,
        "adrs": u.location,  # Assuming email is used as address
        "use_yn": "N"  # Default to "N" as these users are removed
    } for u in frappe.get_all("User", fields=["name", "full_name", "email", "location"])}

    # Find added and removed users
    previous_users = set(doc.custom_previous_branch_users.split(", ") if doc.custom_previous_branch_users else [])
    current_users = set(user_list)
    added_users = current_users - previous_users
    removed_users = previous_users - current_users

    changes = []

    # Process added users
    for user in added_users:
        if user in all_users:
            changes.append({
                "user_id": user,
                "change_type": "added",
                "user_name": all_users[user]["user_name"],
                "adrs": all_users[user]["adrs"],
                "use_yn": "Y"
            })

    # Process removed users
    for user in removed_users:
        if user in all_users:
            changes.append({
                "user_id": user,
                "change_type": "removed",
                "user_name": all_users[user]["user_name"],
                "adrs": all_users[user]["adrs"],
                "use_yn": "N"
            })
    return changes


@frappe.whitelist()
def initialize():

    updated_codes = update_codes(initialize=True)
    updated_item_classes = update_item_classes(initialize=True)
    updated_branches = update_branches(initialize=True)
    
    if updated_codes and updated_item_classes and updated_branches:
        frappe.msgprint("Updated", indicator='green', alert=True)
    else:
        frappe.msgprint("Update incomplete", indicator='orange', alert=True)

@frappe.whitelist()
def sync_dependancies():
    updated_codes = update_codes()
    updated_item_classes = update_item_classes()
    updated_branches = update_branches()

    if updated_codes and updated_item_classes and updated_branches:
        frappe.msgprint("Synchronization Complete", alert=True)
    else:
        frappe.msgprint("Update incomplete", indicator='orange', alert=True)   



@frappe.whitelist()
def sync_branches():
    updated_branches = update_branches()    
    if updated_branches:
        frappe.msgprint("Updated", alert=True)
    else:
        frappe.msgprint("Update incomplete", indicator='orange', alert=True)

def get_company_by_tpin(tpin):
    companies = {d.tax_id: d for d in frappe.get_all("Company", fields=["name", "tax_id"])}

    company = companies.get(tpin)
    if company:
        return company
    else:
        return None
        

def update_branches(initialize=False):
    data = get_branches(initialize=True)

    if not data:
        return
    if data.get("resultCd") not in ("000", "001", "801", "802", "803", "805") or data.get("data") == None:
        return

    # check if branches already exist, if not, insert
    # if exist, update if anything is different
    
    # Fetch all existing branches
    existing_branches = {d.branch: d for d in get_saved_branches()}
    statuses = {d.cd: d for d in frappe.get_all("Code", fields=["name", "cd"], filters={"cd_cls": "09"})}
    if not statuses:
        frappe.throw("Initialize ZRA data first")

    for branch_data in data['data']['bhfList']:

        tpin = branch_data.get('tpin', branch_data.get('tin', None))

        company = get_company_by_tpin(tpin)    
        if company:
            company = company.name
        else:
            frappe.throw(f"There is no company with TPIN {tpin}")

        is_hq = 1 if branch_data.get('hqYn', "N") == "Y" else 0

        status = None
        status_cd = branch_data.get('bhfSttsCd')
        if status_cd:
            status = statuses.get(status_cd).name

        if branch_data['bhfNm'] not in existing_branches:

            new_branch = frappe.get_doc({
                "doctype": "Branch",
                "custom_company": company,
                "branch": branch_data['bhfNm'],
                "custom_bhf_id": branch_data['bhfId'],
                "custom_tpin": tpin,
                "custom_hq_yn": is_hq,
                "custom_branch_status": status,
                "custom_prvnc_nm": branch_data.get('prvncNm', None),
                "custom_dstrt_nm": branch_data.get('dstrtNm', None),
                "custom_sctr_nm": branch_data.get('sctrNm', None),
                "custom_loc_desc": branch_data.get('locDesc', None),
                "custom_mgr_nm": branch_data.get('mgrNm', None),
                "custom_manager_phone_number": branch_data.get('mgrTelNo', None),
                "custom_mgr_email": branch_data.get('mgrEmail', None)

            })
            new_branch.flags.ignore_mandatory = True
            new_branch.insert(ignore_permissions=True)
        else:
            if existing_branches[branch_data['bhfNm']]:
                if (existing_branches[branch_data['bhfNm']].custom_bhf_id != branch_data['bhfId'] or 
                    existing_branches[branch_data['bhfNm']].custom_tpin != tpin or 
                    existing_branches[branch_data['bhfNm']].custom_hq_yn != is_hq or 
                    existing_branches[branch_data['bhfNm']].status != status or 
                    existing_branches[branch_data['bhfNm']].custom_prvnc_nm != branch_data.get('prvncNm', None) or 
                    existing_branches[branch_data['bhfNm']].custom_dstrt_nm != branch_data.get('dstrtNm', None) or 
                    existing_branches[branch_data['bhfNm']].custom_sctr_nm != branch_data.get('sctrNm', None) or 
                    existing_branches[branch_data['bhfNm']].custom_loc_desc != branch_data.get('locDesc', None) or 
                    existing_branches[branch_data['bhfNm']].custom_mgr_nm != branch_data.get('mgrNm', None) or 
                    existing_branches[branch_data['bhfNm']].custom_mgr_tel_no != branch_data.get('mgrTelNo', None) or 
                    existing_branches[branch_data['bhfNm']].custom_mgr_email != branch_data.get('mgrEmail', None)):

                    branch = frappe.get_doc("Branch", branch_data['bhfNm'])
                    branch.update({
                        "custom_bhf_id": branch_data['bhfId'],
                        "custom_company": company,
                        "custom_tpin": tpin,
                        "custom_hq_yn": is_hq,
                        "custom_branch_status": status,
                        "custom_prvnc_nm": branch_data.get('prvncNm', None),
                        "custom_dstrt_nm": branch_data.get('dstrtNm', None),
                        "custom_sctr_nm": branch_data.get('sctrNm', None),
                        "custom_loc_desc": branch_data.get('locDesc', None),
                        "custom_mgr_nm": branch_data.get('mgrNm', None),
                        "custom_manager_phone_number": branch_data.get('mgrTelNo', None),
                        "custom_mgr_email": branch_data.get('mgrEmail', None)
                    })
                    branch.flags.ignore_mandatory = True
                    branch.save(ignore_permissions=True)    
    return True


def update_item_classes(initialize=False):
    """
    1. Fetch item classes from API
    2. Compare with saved item classes
    3. If not saved, insert
    4. If saved, update if anything is different
    """
    data = get_item_classes(initialize)

    if not data or not data.get("data"):
        return


    # If we've reached here, we have a successful response
    # Proceed with processing the data
        
    item_class_list = data['data'].get('itemClsList', [])

    # Fetch all existing item classes
    existing_item_classes = {d.name: d for d in frappe.get_all("Item Class", fields=["name", "item_cls_cd", "item_cls_nm"])}
    tax_types = {d.custom_cd: d for d in frappe.get_all("Tax Category", fields=["title", "custom_cd"])}

    # Update Item Classes
    for item_class_data in item_class_list:
        # Get the tax type title based on the taxTyCd
        tax_type_title = None
        if item_class_data.get('taxTyCd'):
            tax_type = tax_types.get(item_class_data['taxTyCd'])
            if tax_type:
                tax_type_title = tax_type.title

        use_yn = 1 if item_class_data.get('useYn', "Y") == "Y" else 0
        mjr_tg_yn = 1 if item_class_data.get('mjrTgYn', "N") == "Y" else 0

        if item_class_data['itemClsCd'] not in existing_item_classes:
            frappe.get_doc({
                "doctype": "Item Class",
                "item_cls_cd": item_class_data['itemClsCd'],
                "item_cls_nm": item_class_data['itemClsNm'],
                "item_cls_lvl": item_class_data.get('itemClsLvl', None),
                "tax_ty_cd": tax_type_title,
                "use_yn": use_yn,
                "mjr_tg_yn": mjr_tg_yn
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        else:
            existing_class = existing_item_classes[item_class_data['itemClsCd']]
            if (existing_class.item_cls_nm != item_class_data['itemClsNm'] or 
                    existing_class.item_cls_lvl != item_class_data.get('itemClsLvl', None) or 
                    existing_class.tax_ty_cd != item_class_data.get('taxTyCd', None) or 
                    existing_class.use_yn != use_yn or 
                    existing_class.mjr_tg_yn != mjr_tg_yn):
                
                doc = frappe.get_doc("Item Class", item_class_data['itemClsCd'])
                doc.item_cls_nm = item_class_data['itemClsNm']
                doc.item_cls_lvl = item_class_data.get('itemClsLvl', None)
                doc.tax_type = tax_type_title
                doc.use_yn = use_yn
                doc.mjr_tg_yn = mjr_tg_yn
                doc.flags.ignore_mandatory = True
                doc.save(ignore_permissions=True)

    frappe.db.commit()
    frappe.msgprint("Item Classes updated successfully", alert=True)
    return True

   
def get_item_classes(initialize=False):
    response = api("/api/method/smart_invoice_api.api.select_item_classes", {
        "bhf_id": "000"
    }, initialize)
    return validate_api_response(response)

def update_codes(initialize=False):
    """ 
    1. code classes
        update codes from api
        fetch code classes from api
        compare with saved code classes
        if not saved, insert
        if saved, update if anything is different
    2. codes
        for each code class, iterate through its codes
        if code not saved, insert
        if code saved, update if anything is different
    """
    fetched_data = get_codes(initialize)
    # Check if the API call was successful
    if not fetched_data:
        return None
    
    if fetched_data.get('response', None):
        fetched_data = fetched_data.get('response')
    else:
        result_cd = fetched_data.get('resultCd', None)
        error = fetched_data.get('error', None)

        if not result_cd:
            
            if error:
                error_info = {
                    'status_code': fetched_data.get('status_code', 'ERR'),
                    'message': error,
                    'response': fetched_data.get('response', 'No details provided.'),
                    'environment': get_settings().environment,
                    'suppress_msgprint': True
                }
            else:
                error_info = {
                    'status_code': 'No Result Code',
                    'message': 'API response did not include a result code',
                    'response': str(fetched_data),
                    'environment': get_settings().environment,
                    'suppress_msgprint': True
                }
        elif result_cd != '000':
            error_info = {
                'status_code': result_cd,
                'message': fetched_data.get('resultMsg', 'API call was not successful'),
                'response': str(fetched_data),
                'environment': get_settings().environment,
                'suppress_mssgprint': False
            }
        
        if 'error_info' in locals():
            error_handler(error_info)
            return

    # If we've reached here, we have a successful response
    # Proceed with processing the data
    
    cls_list = fetched_data['data'].get('clsList', [])

    # Fetch all existing code classes and codes
    existing_classes = {d.name: d for d in frappe.get_all("Code Class", fields=["name", "cd_cls_nm", "mapped_doctype"])}
    existing_codes = {d.name: d for d in frappe.get_all("Code", fields=["name", "cd", "cd_cls", "cd_nm", "user_dfn_cd1"])}

    # Update Code Classes
    for class_data in cls_list:
        if class_data['cdCls'] not in existing_classes:
            frappe.get_doc({
                "doctype": "Code Class",
                "cd_cls": class_data['cdCls'],
                "cd_cls_nm": class_data['cdClsNm'],
                "usr_dfn_cd1": class_data.get('usrDfnCd1', '')
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        else:
            existing_class = existing_classes[class_data['cdCls']]
            if existing_class.cd_cls_nm != class_data['cdClsNm']:
                doc = frappe.get_doc("Code Class", class_data['cdCls'])
                doc.cd_cls_nm = class_data['cdClsNm']
                doc.flags.ignore_mandatory=True
                doc.save(ignore_permissions=True)

        mapped_doctype = None
        if existing_classes[class_data['cdCls']].mapped_doctype:
            mapped_doctype = existing_classes[class_data['cdCls']].mapped_doctype
        else:
            continue

        # Update Codes
        for code_data in class_data.get('dtlList', []):
            # Create a lowercase version of the name for case-insensitive comparison
            name_lower = f'{class_data["cdCls"]}-{code_data["cd"]}-{code_data["cdNm"]}'.lower()
            
            # Find a matching name in existing_codes, ignoring case
            matching_name = next((key for key in existing_codes if key.lower().strip() == name_lower.strip()), None)
            
            # Use the matching name if found, otherwise create a new name
            name = matching_name if matching_name else f'{class_data["cdCls"]}-{code_data["cd"]}-{code_data["cdNm"]}'
            
            try:
                if matching_name is None:
                    new_code = frappe.get_doc({
                        "doctype": "Code",
                        "cd": code_data['cd'],
                        "cd_cls": class_data['cdCls'],
                        "cd_nm": code_data['cdNm'],
                        "user_dfn_cd1": code_data.get('userDfnCd1', None)
                    })
                    if mapped_doctype:
                        new_code.mapped_doctype = mapped_doctype
                    new_code.insert(ignore_permissions=True, ignore_mandatory=True)
                else:
                    update_code(name, code_data, class_data, existing_codes, mapped_doctype)
            except frappe.exceptions.DuplicateEntryError as e:
                update_code(name, code_data, class_data, existing_codes, mapped_doctype)
    frappe.db.commit()
    return True

def update_code(name, code_data, class_data, existing_codes, mapped_doctype=None):
    existing_code = frappe.get_doc("Code", name)

    if not existing_code:
        return

    if (existing_code.cd_cls != class_data['cdCls'] or
        existing_code.cd_nm != code_data['cdNm'] or
        existing_code.user_dfn_cd1 != code_data.get('userDfnCd1', None) or
        existing_code.mapped_doctype != mapped_doctype):

        doc = frappe.get_doc("Code", existing_code.name)
        doc.cd_cls = class_data['cdCls']
        doc.cd_nm = code_data['cdNm']
        doc.user_dfn_cd1 = code_data.get('userDfnCd1', None)
        if mapped_doctype:
            doc.mapped_doctype = mapped_doctype
        doc.flags.ignore_mandatory=True
        try:
            doc.save(ignore_permissions=True)
        except frappe.exceptions.LinkValidationError as e:
            frappe.msgprint(str(e))
        except Exception as e:
            frappe.msgprint(str(e))

        
def get_codes(initialize=False, validate=True):
    response = api("/api/method/smart_invoice_api.api.select_codes", {
        "bhf_id": "000"
    }, initialize)
    if validate:
        return validate_api_response(response)
    else:
        return response


def validate_api_response(fetched_data):
    if not fetched_data:

        return None

    try:
        response_json = fetched_data if isinstance(fetched_data, dict) else json.loads(fetched_data)
        
        response = response_json.get('response', None)
        if type(response) == str:
            response = json.loads(response)
        
        result_cd = response.get('resultCd')
        result_msg = response.get('resultMsg')

        if result_cd in ('000', '001', '801', '802', '803', '805'):
            return response

        error_messages = {
            '894': "Unable to connect to the Smart Invoice Server",
            '899': "Smart Invoice device error",
            '10000': result_msg
        }
        
        error_info = {
            'status_code': result_cd,
            'message': error_messages.get(result_cd, f'API call was not successful: {result_msg}') + f" ({result_cd})",
            'response': str(response_json),
            'environment': get_settings().environment,
            'suppress_msgprint': result_cd not in ('894', '899', '10000')
        }
        error_handler(error_info)
        return None

    except json.JSONDecodeError as e:
        error_info = {
            'status_code': 'JSON Parse Error',
            'message': f'Failed to parse API response as JSON: {str(e)}',
            'response': fetched_data,
            'environment': get_settings().environment,
            'suppress_msgprint': False
        }
        error_handler(error_info)
        return None
    except Exception as e:
        error_info = {
            'status_code': 'Unexpected Error',
            'message': f'An unexpected error occurred: {str(e)}',
            'response': fetched_data,
            'environment': get_settings().environment,
            'suppress_msgprint': False
        }
        error_handler(error_info)
        # import traceback
        # error_traceback = traceback.format_exc()
        # print(f"{str(e)}\n\nTraceback:\n{error_traceback}")
        return None
        

@frappe.whitelist()
def test_connection():   
    # verify_site_encryption()

    # codes = get_codes(validate=False)
    response = get_branches()

    if response:
        if response and response.get('error', response) != "Smart Invoice VSDC Timeout":
            if response and not response.get('error') and response.get('resultCd') in ["000", "001"]:
                frappe.msgprint("Connection Successful", indicator='green', alert=True)
                return True
    frappe.msgprint("Connection Failure", indicator='red', alert=True)
    return False