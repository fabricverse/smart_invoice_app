import frappe
from datetime import datetime
import requests, json
from frappe.exceptions import AuthenticationError
from requests.exceptions import JSONDecodeError
from frappe.utils import cstr
import inspect
from frappe.utils.password import get_decrypted_password, get_encryption_key

frappe.whitelist()
def get_settings():
    return frappe.get_doc("Smart Invoice Settings", "Smart Invoice Settings")

"""global method to convert date to yyyymmddmmss"""
def api_date_format(date):
    if type(date) == str:
        date = datetime.strptime(date.split('.')[0], "%Y-%m-%d %H:%M:%S")
    elif type(date) != datetime:
        frappe.throw("Invalid date type")
    return date.strftime("%Y%m%d%H%M%S")

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

def api_call(endpoint, data, initialize=False): 
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
            "vsdc_serial": settings.vsdc_serial,
            "tpin": settings.tpin
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
    branches = frappe.get_all("Branch", fields=["branch", "custom_bhf_id", "custom_tpin", "custom_hq_yn", "custom_prvnc_nm", "custom_dstrt_nm", "custom_sctr_nm", "custom_loc_desc", "custom_mgr_nm", "custom_mgr_tel_no", "custom_mgr_email"])
    if not branches:
        branch = frappe.new_doc("Branch")
        branch.custom_bhf_id = "000"
        return [branch]
    return branches

def get_branches(initialize=False):
    saved_branches = get_saved_branches()

    response = api_call("/api/method/smart_invoice_api.api.select_branches", {
        "bhf_id": saved_branches[0].custom_bhf_id
    }, initialize)

    return validate_api_response(response)

def get_user_branches():
    branches = frappe.get_all("Branch", fields=["branch", "custom_bhf_id", "custom_tpin"], limit=0)
    branch_users = frappe.get_all("Branch User", fields=["*"], filters={"user_id": ("in", [frappe.session.user])}, limit=0)

    branch_data = []
    for branch in branches:
        for bu in branch_users:
            branch_data.append({
                "branch": branch.branch,
                "custom_bhf_id": branch.custom_bhf_id,
                "custom_tpin": branch.custom_tpin,
                "user_id": bu.user_id
            })
        branch_data.append({
            "branch": branch.branch,
            "custom_bhf_id": branch.custom_bhf_id,
            "custom_tpin": branch.custom_tpin,
            "user_id": "Administrator"
        })


    print(branch_data)
        

    # return branches[0] if branches else None

def is_migration():
    stack = inspect.stack()
    return any(frame.function == 'migrate' for frame in stack)

@frappe.whitelist()
def save_item_api(item, unit=None, pkg_unit=None, branch=None):
    if not item:
        return
    if type(item) == str:
        frappe.get_doc("Item", item)

    branches = []
    if branch:
        branches = [branch]
    else:
        branches = get_user_branches()
    
    if not unit or not pkg_unit:
        # check if item has a unit_code
        if item.custom_unit_code and item.custom_pkg_unit_code:
            unit = item.custom_unit_code
            pkg_unit = item.custom_pkg_unit_code    
        elif not item.uom or not item.custom_pkg_unit:
            frappe.throw("Smart Invoice requires a UOM and Package UOM for Item {0}".format(frappe.bold(item.item_code)))
        else:
            unit, pkg_unit = get_unit_code(item)

    return

    tax_code = get_tax_code(item)
    batch = get_batch_no(item)
    barcode = get_barcode(item)
    default_price = get_item_price(item)
    
    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    for branch in branches:
        data = {        
            "tpin": branch.custom_tpin,
            "bhfId": branch.custom_bhf_id,
            "itemCd": item.item_code,
            "itemClsCd": item.custom_item_cls_cd,
            "itemTyCd": item.item_ty,
            "itemNm": item.item_name,
            "itemStdNm": item.item_name,
            "orgnNatCd": item.custom_orgn_nat,
            "pkgUnitCd": item.custom_pkg_unit,
            "qtyUnitCd": unit,
            "vatCatCd": tax_code,
            "iplCatCd": tax_code,
            "tlCatCd": tax_code,
            "exciseTxCatCd": item.custom_excise_tx_cat_cd,
            "btchNo": batch,
            "bcd": barcode,
            "dftPrc": default_price,
            "manufacturerTpin": item.custom_manufacturer_tpin,
            "manufactureritemCd": item.custom_manufacture_item_cd,
            "rrp": item.default_sell_price, #
            "svcChargeYn": "N" if item.custom_svc_charge_yn == 0 else "Y",
            "rentalYn": "N" if item.custom_rental_yn == 0 else "Y",
            "addInfo":item.description,
            "sftyQty": item.safety_stock,
            "isrcAplcbYn": "N" if item.custom_isrc_aplc_b_yn == 0 else "Y",
            "useYn": "Y" if item.disabled == 1 else "N",        
            "regrNm": users[item.owner].full_name,
            "regrId": item.owner,
            "modrNm": users[frappe.session.user].full_name,
            "modrId": frappe.session.user
        }
        print(data)
        return
    response = save_branch_customer_api(data)
    if response.get("resultCd") == "000":
        frappe.set_value("Customer Branch", branch.get("name"), "custom_synchronized", 1)      
        frappe.msgprint(f"Synchronized branch details on Smart Invoice", indicator='green', alert=True)
    else:
        frappe.msgprint(f"Failed to synchronize branch details on Smart Invoice, try again in a few minutes.", indicator='red', alert=True)

    response = api_call("/api/method/smart_invoice_api.api.save_item", item)
    return validate_api_response(response)

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
    response = api_call("/api/method/smart_invoice_api.api.save_branche_customer", data)
    return validate_api_response(response)

@frappe.whitelist()
def get_customer_api(customer, branch="Headquarter"):  # incomplete
    customer = validate_customer(customer)
    frappe.throw(f"Incomplete")

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
    print(data)
    return
    response = api_call("/api/method/smart_invoice_api.api.select_customer", data)
    return validate_api_response(response)



@frappe.whitelist()
def save_customer_api(customer, company=None, branch=None):

    if not customer or not customer.custom_customer_branches:
        return
    
    custom_bhf_id = branch.custom_bhf_id if branch else "000"
    custom_tpin = company.tax_id if company else "000"
    users = {d.name: d for d in frappe.get_all("User", fields=["name", "full_name"])}
    address = ""
    contact = frappe.get_doc("Contact", customer.contact_person)
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
    response = api_call("/api/method/smart_invoice_api.api.save_branche_customer", data)
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

    response = api_call("/api/method/smart_invoice_api.api.save_branche_user", data)
    return validate_api_response(response)


@frappe.whitelist()
def update_api_users(branch):

    doc = frappe.get_doc("Branch", branch)
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
    response = api_call("/api/method/smart_invoice_api.api.select_item_classes", {
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
    response = api_call("/api/method/smart_invoice_api.api.select_codes", {
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
            '899': "Smart Invoice device error"
        }
        
        error_info = {
            'status_code': result_cd,
            'message': error_messages.get(result_cd, f'API call was not successful: {result_msg}') + f" ({result_cd})",
            'response': str(response_json),
            'environment': get_settings().environment,
            'suppress_msgprint': result_cd not in ('894', '899')
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
        # frappe.throw(str(e))
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
    print("codes", str(codes)[:500])
    return codes