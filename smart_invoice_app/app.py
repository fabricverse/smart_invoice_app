import frappe
from datetime import datetime
import requests, json
from frappe.exceptions import AuthenticationError
from requests.exceptions import JSONDecodeError
from frappe.utils import cstr

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

def error_handler(error_info):
    """
    Generic error handler function.
    Shows msgprint only if env = sandbox.
    Returns an error dictionary.
    """
    status_code = error_info.get('status_code', 'ERR')
    message = error_info.get('message', 'An unexpected error occurred.')
    
    # Log the error
    frappe.log_error(
        message=f"Error: {status_code} - {message}",
        title="API Call Error"
    )
    
    # Show msgprint only if env is sandbox
    if error_info.get('environment') == 'Sandbox': # frappe.conf.get('developer_mode') or
        frappe.msgprint(f"Error {status_code}: {message}", indicator='red', alert=True)
    
    return {"error": message, "status_code": status_code}

def api_call(end_point, data): 
    
    settings = get_settings()
    base_url = settings.base_url
    secret = settings.get_password("api_secret")
    frappe.errprint(data)

    error_messages = {
        400: "Bad Request",
        401: "Authentication failed. Please check your API credentials.",
        403: "Forbidden. Please check your API credentials.",
        404: "API endpoint not found.",
        415: "Unsupported Media Type.",
        422: "Unprocessable Entity.",
        500: "Internal Server Error."
    }

    try:
        r = requests.post(
            base_url + end_point,
            data=data,
            headers={
                "Authorization": f'token {settings.api_key}:{secret}',
                "Content-Type": "application/json"
            }
        )
        
        if r.status_code == 200:
            response_json = r.json()
            return response_json.get("message", response_json)
        else:
            error_info = {
                'status_code': r.status_code,
                'message': error_messages.get(r.status_code, cstr(r.text)),
                'environment': settings.environment
            }
            return error_handler(error_info)

    except AuthenticationError as e:
        error_info = {
            'status_code': getattr(e.response, 'status_code', 'AuthenticationError'),
            'message': str(e),
            'environment': settings.environment
        }
        return error_handler(error_info)
    except JSONDecodeError as e:
        error_info = {
            'status_code': 'AuthenticationError',
            'message': f"JSONDecodeError: {str(e)}",
            'environment': settings.environment
        }
        return error_handler(error_info)
    except Exception as e:
        error_info = {
            'status_code': 'AuthenticationError',
            'message': f"An unexpected error occurred: {str(e)}",
            'environment': settings.environment
        }
        return error_handler(error_info)

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
    fetched_code_classes = get_codes()
    frappe.errprint(str(fetched_code_classes))
    # saved_code_classes = frappe.get_all("Code Class", fields=[])
    # codes = frappe.get_all("Code", fields=[])

    # for code_class in fetched_code_classes:
    #     if code_class not in saved_code_classes:
    #         frappe.get_doc({
    #             "doctype": "Code Class",
    #         }).insert()
    #     else:
    #         # update any changes
    #         pass

    #     for code in fetched_codes:
        

def get_codes():
    settings = get_settings()

    data = json.dumps({
        "tpin": settings.tpin,
        "bhf_id": "000"
    })

    codes = api_call("/api/method/smart_invoice_api.api.select_codes", data=data)    
    return codes

@frappe.whitelist()
def run_test():   
    print("run_test")
    

    codes = get_codes()

    frappe.errprint(codes)
    frappe.msgprint("Connection Successful")
    
    return codes