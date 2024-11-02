
import io
import os
import frappe
from base64 import b64encode
from frappe import _
from datetime import datetime
import requests, json
from frappe.exceptions import AuthenticationError
from requests.exceptions import JSONDecodeError
from frappe.utils import cstr, now_datetime, flt
import inspect
from frappe.utils.password import get_decrypted_password, get_encryption_key
import re

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.data import add_to_date, get_time, getdate
from pyqrcode import create as qr_create

from erpnext import get_region



"""global method to convert date to yyyymmddmmss"""
def api_date_format(date, date_only=False):
    if type(date) == str and not date_only:
        date = datetime.strptime(date.split('.')[0], "%Y-%m-%d %H:%M:%S")
    elif type(date) == str and date_only:
        date = datetime.strptime(date, "%Y-%m-%d")
    elif type(date) != datetime:
        frappe.throw("Invalid date type")
    return date.strftime("%Y%m%d%H%M%S") if not date_only else date.strftime("%Y%m%d")

    
frappe.whitelist()
def get_settings():
    return frappe.get_cached_doc("Smart Invoice Settings", "Smart Invoice Settings")


def create_qr_code(doc, invoice_url=None):
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
                    # allow_on_submit=1
                )
            ]
        })

    # Don't create QR Code if it already exists
    qr_code = doc.get("invoice_qr_code")
    if qr_code and frappe.db.exists({"doctype": "File", "file_url": qr_code}):
        return

    meta = frappe.get_meta(doc.doctype)

    if "invoice_qr_code" in [d.fieldname for d in meta.get_image_fields()]:

        # invoice_url = "https://sandboxportal.zra.org.zm/common/link/ebm/receipt/indexEbmReceiptData?Data=2295829289000NHYNHV6VNX7UN77I"

        qr_image = io.BytesIO()
        url = qr_create(invoice_url, error='L')
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
        doc.db_set('invoice_qr_code', _file.file_url)
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
            branches = get_user_branches()
            data.update({
                "bhfId": branches[0].get("custom_bhf_id")
            })
        
        if not data.get("tpin"):
            if not branches:
                branches = get_user_branches()
            data.update({
                "tpin": branches[0].get("custom_tpin")
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
    branches = frappe.get_all("Branch", fields=["*"], limit=0)
    if not branches:
        branch = frappe.new_doc("Branch")
        branch.custom_bhf_id = "000"
        return [branch]
    return branches

def get_branches(initialize=False): # review
    saved_branches = get_saved_branches()

    response = api("/api/method/smart_invoice_api.api.select_branches", {
        "bhf_id": saved_branches[0].custom_bhf_id
    }, initialize)

    return validate_api_response(response)

@frappe.whitelist()
def save_invoice_api(invoice, method=None, branch=None):
    
    invoice_data = prepare_invoice_data(invoice, branch=branch)    
    endpoint = "/api/method/smart_invoice_api.api.save_sales"

    response = api(endpoint, invoice_data)
    data = response.get("response_data")
    json_data = json.loads(data)

    if json_data.get("resultCd") == "000":
        create_qr_code(invoice, invoice_url=json_data.get("data").get("qrCodeUrl"))
    else:
        frappe.msgprint(_(f"Message: {json_data.get('resultMsg')}"), title="Smart Invoice Failure")

        frappe.msgprint(data)
        frappe.msgprint(json.dumps(invoice_data))


def get_payment_code(doc):
    if not doc.payments:
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
            elif doc.shipping_address:
                country = get_country_from_address_display(doc.address_display, countries)
            if country:
                country_code = countries[country]

        elif doc.dispatch_address_name:
            if doc.dispatch_address_name:
                country = frappe.get_cached_value("Address", doc.customer_address, "country")
            elif doc.dispatch_address_name:
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
    """sets default item taxe for invoice items if nothing is set
        called on save
    """

    if isinstance(invoice, str):
        invoice = frappe.get_doc("Sales Invoice", invoice)
    else:
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

def prepare_invoice_data(invoice, branch=None):
        
    if isinstance(invoice, str):
        invoice = frappe.get_cached_doc("Sales Invoice", invoice)
    
    if invoice.discount_amount:
        frappe.throw(_("Sorry, invoice level discounting is not yet supported in Smart Invoice. You can set item level discounts instead."), title="Not Supported")
    
    company = frappe.get_cached_doc("Company", invoice.company)
    customer = frappe.get_cached_doc("Customer", invoice.customer)
    
    if not branch:
        branches = get_user_branches()
        branch = next((b for b in branches if b['custom_company'] == invoice.company), None)
        if not branch and not frappe.flags.batch:
            frappe.throw("No branch found for the current user and company")
    
    posting_date = invoice.posting_date
    posting_time = invoice.posting_time or "00:00:00"

    # Group variables that depend on is_return
    if invoice.is_return == 1:
        rcpt_ty_cd = "R"
        sales_stts_cd = "05"
        org_invc_no = invoice.return_against
        rfd_rsn_cd = invoice.custom_refund_reason_code
        rfd_dt = None
        if rfd_rsn_cd:
            rfd_dt = api_date_format(f"{posting_date} {posting_time}")
        cancel_date = get_cancel_date(invoice)
    else:
        rcpt_ty_cd = "S"
        sales_stts_cd = "02"
        org_invc_no = 0
        rfd_dt = None
        rfd_rsn_cd = ""
        cancel_date = None

    tax_data = prepare_tax_data(invoice)
    posting_date_time = api_date_format(f"{posting_date} {posting_time}")
    posting_date_only = api_date_format(posting_date, date_only=True)

    country_code = get_country_code(invoice)
    invoice_name = api_date_format(f"{posting_date} {posting_time}")+"1"
    print("invoice_name", invoice_name)
    
    data = {
        "tpin": branch['custom_tpin'],
        "bhfId": branch['custom_bhf_id'],
        "orgInvcNo": org_invc_no,
        "cisInvcNo": invoice_name,# invoice.name, # 
        "custTpin": customer.tax_id,
        "custNm": customer.customer_name,
        "salesTyCd": "N",  # Assuming normal sale
        "rcptTyCd": rcpt_ty_cd,
        "pmtTyCd": get_payment_code(invoice),
        "salesSttsCd": sales_stts_cd,
        "cfmDt": posting_date_time,
        "salesDt": posting_date_only,
        "stockRlsDt": None if invoice.update_stock == 0 else posting_date_time,
        "cnclReqDt": cancel_date,
        "cnclDt": cancel_date,
        "rfdDt": rfd_dt,
        "rfdRsnCd": rfd_rsn_cd,
        "totItemCnt": len(invoice.items),
        "prchrAcptcYn": "Y",
        "remark": invoice.remarks or "",
        "saleCtyCd": "1",
        "lpoNumber": None, # invoice.po_no or None,
        "destnCountryCd": country_code if not "ZM" else None,
        "currencyTyCd": invoice.currency or "XXX",
        "exchangeRt": invoice.conversion_rate,
        "dbtRsnCd": None,
        "invcAdjustReason": None,
        "cashDcAmt": flt(invoice.discount_amount, 3),
        "cashDcRt": flt(invoice.additional_discount_percentage, 3),

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
    }
    items = []
    
    for idx, item in enumerate(invoice.items, start=1):

        item_doc = frappe.get_cached_doc("Item", item.item_code)
        unit_cd, pkg_unit = get_unit_code(item_doc, invoice.company)
        
        item_data = {
            "itemSeq": idx,
            "itemCd": item.item_code,
            "itemClsCd": item_doc.custom_item_cls_cd or company.custom_default_item_class,
            "itemNm": item.item_code,
            "bcd": None,
            "pkgUnitCd": pkg_unit or "PACK",
            "pkg": flt(item.qty, 3),
            "qtyUnitCd": unit_cd or "U",
            "qty": flt(item.qty, 3),
            "prc": flt(item.rate, 3),
            "splyAmt": flt(item.amount, 3),
            "dcRt": flt(item.discount_percentage, 3) if item.discount_percentage else 0.0,
            "dcAmt": flt(item.discount_amount, 3) if item.discount_amount else 0.0,
            "isrccCd": None,
            "isrccNm": None,
            "rrp": flt(item.rate, 3),
            "isrcRt": 0.0,
            "isrcAmt": 0.0,
            "totAmt": flt(item.amount, 3),
            "vatTaxblAmt": 0.0,
            "vatAmt": 0.0
        }

        # set tax defaults
        code_doc = None        
        if not item_doc.custom_industry_tax_type or not item.item_tax_template or not item.custom_tax_rate or not item.custom_tax_code:
            if not item.custom_tax_code:
                item.custom_tax_code = company.custom_tax_code
                if not item.custom_tax_code:
                    frappe.throw(f"Set <strong>Tax Bracket</strong> in company <a href='{company.get_url()}'>{frappe.bold(invoice.company)}</a>")

            if not item.item_tax_template or not item.custom_tax_rate:
                if item.custom_tax_code:
                    code_doc = frappe.get_cached_value("Code", {"cd": item.custom_tax_code}, ["name", "cd_nm", "user_dfn_cd1"], as_dict=True)
                else:
                    code_doc = frappe.get_cached_doc("Code", company.custom_tax_bracket)

                item.custom_tax_rate  = flt(code_doc.user_dfn_cd1, 2)
                item.item_tax_template = f"{code_doc.cd_nm} - {company.abbr}"           
            
            # do industry tax type helps choose the correct calculation
            if not item_doc.custom_industry_tax_type:
                templates = {
                    f"TOT - {company.abbr}": "TOT",
                    f"Standard Rated(16%) - {company.abbr}": "VAT",
                    f"Minimum Taxable Value (MTV-16%) - {company.abbr}": "VAT",
                    f"Reverse VAT - {company.abbr}": "VAT",
                    f"Disbursement - {company.abbr}": "Zero Rated (VAT)",
                    f"Exempt - {company.abbr}": "Zero Rated (VAT)",
                    f"Zero-rated by nature - {company.abbr}": "Zero Rated (VAT)",
                    f"Zero-rated LPO - {company.abbr}": "Zero Rated (VAT)",
                    f"Exports(0%) - {company.abbr}": "Zero Rated (VAT)",
                    f"Excise Electricity - {company.abbr}": "Excise Duty",
                    f"Excise on Coal - {company.abbr}": "Excise Duty",
                    f"Tourism Levy - {company.abbr}": "Tourism Levy",
                    f"Insurance Premium Levy - {company.abbr}": "Insurance Premium Levy",
                    f"Re-insurance - {company.abbr}": "Insurance Premium Levy"
                }
                # defaults to VAT if no industry tax type is set, VAT will work for VAT and TOT depending on the computed item tax code
                item_doc.custom_industry_tax_type = templates.get(item.item_tax_template, "VAT")


            if item.idx == 1:
                frappe.msgprint("Item Taxes not set. Using company default.", indicator="Warning", alert=True)

        tax_code = item.custom_tax_code.title()

        # Calculate taxes for the item
        if item_doc.custom_industry_tax_type in ["Excise Duty", "Tourism Levy", "Insurance Premium Levy"]:
            tax_types = {
                "Excise Duty": "excise",
                "Tourism Levy": "tl",
                "Insurance Premium Levy": "ipl"
            }

            tax_rate = flt(item.custom_tax_rate)

            amt = flt(item.amount, 4)
            rate = 0.0
            taxable_amount = 0.0
            tax_amt = 0.0
            
            if tax_rate != 0:
                rate = (flt(tax_rate/100) + 1)
                taxable_amount = flt(amt/rate, 4)
                tax_amt = flt(amt - taxable_amount, 4)

            tax_type = tax_types[item_doc.custom_industry_tax_type]

            if item_doc.custom_industry_tax_type in ["Tourism Levy", "Insurance Premium Levy"]:
                if tax_code == "Ipl2":
                    taxable_amount = amt

                item_data.update({
                    f"{tax_type}CatCd": item.custom_tax_code,
                    f"{tax_type}TaxblAmt": taxable_amount,
                    f"{tax_type}Amt": tax_amt
                })
            elif item_doc.custom_industry_tax_type == "Excise Duty":
                item_data.update({
                    f"{tax_type}TxCatCd": item.custom_tax_code,
                    f"{tax_type}TaxblAmt": taxable_amount,
                    f"{tax_type}TxAmt": tax_amt
                })

            # print("tax_type", tax_code)
            # print("rate", rate)
            # print("amt", amt)
            # print("taxable_amount", taxable_amount)
            # print("tax_amt", tax_amt)


            inv_taxable_amount = data[f"taxblAmt{tax_code}"] + taxable_amount
            inv_tax_amount = data[f"taxAmt{tax_code}"] + tax_amt

            tot_taxbl_amt = data[f"totTaxblAmt"] + taxable_amount
            tot_tax_amt = data[f"totTaxAmt"] + tax_amt
            inv_tot_amt = data["totAmt"] + amt

            data.update({
                f"taxblAmt{tax_code}": flt(inv_taxable_amount, 4),
                f"taxAmt{tax_code}": flt(inv_tax_amount, 4),

                f"taxRt{tax_code}": tax_rate,

                "totTaxblAmt": flt(tot_taxbl_amt, 4),
                "totTaxAmt": flt(tot_tax_amt, 4),
                "totAmt": flt(inv_tot_amt, 4)
            })
        elif item_doc.custom_industry_tax_type == "Rental Tax":
            not_supported()
        elif item_doc.custom_industry_tax_type == "Service Tax":
            not_supported()
        else:
            item_taxes = get_item_taxes(item, tax_code)
            item_data.update(item_taxes)
            
            # update each tax item being calculated
            tax_amount = data[f"taxAmt{tax_code}"] + item_taxes.get("vatAmt", 0)
            taxable_amount = data[f"taxblAmt{tax_code}"] + item_taxes.get("vatTaxblAmt", 0)
            total_taxable_amount = data[f"totTaxblAmt"] + item_taxes.get("vatTaxblAmt", 0)
            total_tax_amount = data[f"totTaxAmt"] + item_taxes.get("vatAmt", 0)
            total_amount = data["totAmt"] + item_taxes.get("totAmt", 0)

            # print("tax_type", tax_code)
            # print("rate", item.custom_tax_rate)
            # print("taxable_amount", item_taxes.get("vatTaxblAmt", 0))
            # print("tax_amt", item_taxes.get("vatAmt", 0))

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

    data.update({"itemList": items})
    data.update(get_doc_user_data(invoice)) # add user info

    return data


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
    amt = flt(item.amount, 4)
    
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


def prepare_tax_data(invoice):
    
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


def get_user_branches():
    branches = frappe.get_all("Branch", fields=["branch", "custom_bhf_id", "custom_tpin", "custom_company"], limit=0)
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
    return branch_data


def is_migration():
    stack = inspect.stack()
    return any(frame.function == 'migrate' for frame in stack)

def get_unit_code(item, company):
    """
    - search codes for matching UOM
    - use fallback UOMs if nothting is found
        - smart_invoice_settings.default_uom : suggest each
        - smart_invoice_settings.default_pkg_uom : suggest pack
    """
    codes = frappe.get_all("Code", fields=["name", "cd", "cd_nm", "cd_cls"], filters={"cd_cls": ["in", ["10", "17"]]})

    unit_cd = None
    pkg_unit = None
    for code in codes:
        if (code.cd_nm.lower() == item.stock_uom.lower() or 
                item.stock_uom.lower() in code.cd_nm.lower() or 
                code.cd_nm.lower() in item.stock_uom.lower()):
            unit_cd = code.cd
        if item.custom_pkg_unit:
            if (code.cd_nm.lower() == item.custom_pkg_unit.lower() or 
                    item.custom_pkg_unit.lower() in code.cd_nm.lower() or 
                    code.cd_nm.lower() in item.custom_pkg_unit.lower()):
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
        response = api("/api/method/smart_invoice_api.api.update_item", item)
        item_data.append(validate_api_response(response))
        
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
def sync_items(initialize=False):
    r = get_items_api(initialize=True)
    if not r.get("resultCd") == "000": 
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
            if save_item_api(item):
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
            return False
        frappe.throw("Smart Invoice requires an Item Type for <strong>Item Group {0}</strong>.".format(frappe.bold(item.item_group)))

    item_data = []
    # check if item has a unit_code
    if item.custom_qty_unit_cd and item.custom_pkg_unit_cd:
        unit = item.custom_qty_unit_cd
        pkg_unit = item.custom_pkg_unit_cd
    elif not item.stock_uom or not item.custom_pkg_unit:
        if frappe.flags.skip_failing:
            return False
        frappe.throw("Smart Invoice requires a UOM and Package UOM for Item {0}".format(frappe.bold(item.item_code)))
    else:
        for branch in branches:            
            default_price = get_item_price(item.item_code, branch.get("custom_company"))
            unit, pkg_unit = get_unit_code(item, branch.get("custom_company"))
            data = {        
                "tpin": branch.get("custom_tpin"),
                "bhfId": branch.get("custom_bhf_id"),
                "useYn": "Y" if item.disabled == 0 else "N",
                "itemCd": item.item_code,
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
        response = api("/api/method/smart_invoice_api.api.save_item", item)
        item_data.append(validate_api_response(response))
        
    return item_data


def validate_customer(customer):
    customer = json.loads(customer)

    if customer.get("custom_customer_branches") == None:
        frappe.throw(f"Smart Invoice requires a branch for every customer. Please assign a branch to {frappe.bold(customer.get('customer_name'))}.")
    if customer.get("tax_id") == None or len(customer.get("tax_id")) != 10:
        frappe.throw(f"Smart Invoice requires 10 digit TPIN for {frappe.bold(customer.get('customer_name'))}. This TPIN {frappe.bold(customer.get('tax_id'))} is not valid.")
    return customer


@frappe.whitelist()
def sync_customer_api(customer):
    if not customer:
        return
    
    customer = validate_customer(customer)
    
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

    for branch in customer.get("custom_customer_branches"):
        if branch.get("custom_synchronized") == 0:
            data = {
                "tpin": branch.get("custom_tpin"),
                "bhfId": branch.get("custom_branch_code", "000"),
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
            response = save_branch_customer_api(data)
            if response.get("resultCd") == "000":
                frappe.set_value("Customer Branch", branch.get("name"), "custom_synchronized", 1)      
                frappe.msgprint(f"Synchronized branch details on Smart Invoice", indicator='green', alert=True)
            else:
                frappe.msgprint(f"Failed to synchronize branch details on Smart Invoice, try again in a few minutes.", indicator='red', alert=True)
    return True

def save_branch_customer_api(data):
    response = api("/api/method/smart_invoice_api.api.save_branche_customer", data)
    return validate_api_response(response)

@frappe.whitelist()
def get_customer_api(customer, branch="Headquarter"):  # incomplete
    customer = validate_customer(customer)
    frappe.throw(f"Function is incomplete")

    branches = [d.branch for d in customer.get("custom_customer_branches")]
    if not branches:
        branches = [json.dumps(d) for d in frappe.get_all("Branch", fields=["branch", "custom_bhf_id", "custom_tpin"], filters={"branch": branch})]

    if not customer:
        return
    data = {
        "tpin": branches[0].get("custom_tpin"),
        "bhfId": branches[0].get("custom_bhf_id"),
        "custmTpin": customer.tax_id
    }
    
    response = api("/api/method/smart_invoice_api.api.select_customer", data)
    return validate_api_response(response)



@frappe.whitelist()
def save_customer_api(customer, company=None, branch=None):

    if not customer or not customer.custom_customer_branches:
        return
    
    custom_bhf_id = branch.custom_bhf_id if branch else "000"
    custom_tpin = company.tax_id if company else "000"
    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    address = ""
    contact = frappe.get_cached_doc("Contact", customer.contact_person)
    mobile_no = customer.mobile_no
    email = customer.email_id
    data={
        "tpin": company.tax_id,
        "bhfId": branch.custom_bhf_id,
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
    return validate_api_response(response)


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

    if not data or data.get("data") == None:
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
    
    if fetched_data.get('response_data', None):
        fetched_data = fetched_data.get('response_data')
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
    existing_code = existing_codes[name]

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
        doc.save(ignore_permissions=True)
        
def get_codes(initialize=False):
    response = api("/api/method/smart_invoice_api.api.select_codes", {
        "bhf_id": "000"
    }, initialize)

    return validate_api_response(response)


def validate_api_response(fetched_data):
    if not fetched_data:

        return None

    try:
        response_json = fetched_data if isinstance(fetched_data, dict) else json.loads(fetched_data)
        
        response_data = response_json.get('response_data', None)
        if type(response_data) == str:
            response_data = json.loads(response_data)
        
        result_cd = response_data.get('resultCd')
        result_msg = response_data.get('resultMsg')

        if result_cd in ('000', '001', '801', '802', '803', '805'):
            return response_data

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
    codes = get_codes()
    
    if codes:
        if not codes.get('error'):
            frappe.msgprint("Connection Successful", indicator='green', alert=True)
        else:
            frappe.msgprint("Connection Failure", indicator='red', alert=True)
    else:
        frappe.msgprint("Connection Failure", indicator='red', alert=True)
    return codes
    
    # if 'error_info' in locals():
    #     error_handler(error_info)
    #     return None



@frappe.whitelist()
def test_connection():   
    # verify_site_encryption()

    codes = get_codes()

    if codes:
        if not codes.get('error'):
            frappe.msgprint("Connection Successful", indicator='green', alert=True)
        else:
            frappe.msgprint("Connection Failure 1", indicator='red', alert=True)
    else:
        frappe.msgprint("Connection Failure", indicator='red', alert=True)
    return codes