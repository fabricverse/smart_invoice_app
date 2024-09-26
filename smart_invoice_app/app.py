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
        message=f"Error: {status_code} - {message}",
        title="API Call Error"
    )

    # Check if the function is called from test_connection
    called_from_test = any('test_connection' in frame.function for frame in inspect.stack())
    
    # Show msgprint if env is sandbox or if called from test_connection
    if error.get('environment') == 'Sandbox' or called_from_test:
        if isinstance(status_code, int):
            msg = message
        else:
            msg = response
        if not error.get('suppress_msgprint'):
            frappe.msgprint(msg=str(msg), title=f"Something went wrong: {error.get('status_code')}", indicator='red')
    
    return {"error": message, "status_code": status_code, "response": response}

def api_call(endpoint, data): 
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
        500: "Internal Server Error."
    }

    try:
        data.update({
            "default_server": settings.default_server,
            "vsdc_serial": settings.vsdc_serial,
            "tpin": settings.tpin
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

@frappe.whitelist()
def next_feature_test():
    update_codes()

def update_codes():
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
    fetched_data = get_codes()
    # Check if the API call was successful
    
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
    print(fetched_data)

    fetched_data = json.loads(fetched_data)
    
    cls_list = fetched_data['data'].get('clsList', [])

    # Fetch all existing code classes and codes
    existing_classes = {d.name: d for d in frappe.get_all("Code Class", fields=["name", "cd_cls_nm"])}
    existing_codes = {d.name: d for d in frappe.get_all("Code", fields=["name", "cd", "cd_cls", "cd_nm", "user_dfn_cd1"])}

    # print(existing_codes)
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
                doc.save(ignore_permissions=True, ignore_mandatory=True)

        # Update Codes
        for code_data in class_data.get('dtlList', []):
            name = f'{class_data["cdCls"]}-{code_data["cd"]}-{code_data["cdNm"]}'

            if name not in existing_codes:

                frappe.get_doc({
                    "doctype": "Code",
                    "cd": code_data['cd'],
                    "cd_cls": class_data['cdCls'],
                    "cd_nm": code_data['cdNm'],
                    "user_dfn_cd1": code_data.get('userDfnCd1', None)
                }).insert(ignore_permissions=True, ignore_mandatory=True)

            else:
                existing_code = existing_codes[name]

                if (existing_code.cd_cls != class_data['cdCls'] or
                    existing_code.cd_nm != code_data['cdNm'] or
                    existing_code.user_dfn_cd1 != code_data.get('userDfnCd1', None)):

                    doc = frappe.get_doc("Code", existing_codes['name'])
                    doc.cd_cls = class_data['cdCls']
                    doc.cd_nm = code_data['cdNm']
                    doc.user_dfn_cd1 = code_data.get('userDfnCd1', None)
                    doc.save(ignore_permissions=True, ignore_mandatory=True)

    frappe.db.commit()
    frappe.msgprint("Codes updated successfully", alert=True)

def get_codes():
    return api_call("/api/method/smart_invoice_api.api.select_codes", {
        "bhf_id": "000"
    })

@frappe.whitelist()
def test_connection():   
    # verify_site_encryption()

    codes = get_codes()
        
    if not codes.get('error'):
        frappe.msgprint("Connection Successful", indicator='green', alert=True)
    else:
        frappe.msgprint("Connection Failure", indicator='red', alert=True)
    print(str(codes)[:500])
    return codes
