import frappe
from datetime import datetime
import requests, json

"""global method to convert date to yyyymmddmmss"""
def api_date_format(date):
    if type(date) == str:
        date = datetime.strptime(date.split('.')[0], "%Y-%m-%d %H:%M:%S")
    elif type(date) != datetime:
        frappe.throw("Invalid date type")
    return date.strftime("%Y%m%d%H%M%S")


frappe.whitelist()
def get_boot_data():
    boot = {}
    settings = frappe.get_single("Smart Invoice Settings")
    boot["settings"] = settings
    return boot

def get_codes():

    boot = get_boot_data()
    settings = boot["settings"]
    base_url = settings.base_url
    secret = settings.get_password("api_secret")

    headers = {
        "Authorization": 'token {api_key}:{api_secret}'.format(api_key=settings.api_key, api_secret=secret),
        "Content-Type": "application/json"
    }

    data = json.dumps({
        "tpin": settings.tpin,
        "bhf_id": "000"
    })

    r = requests.get(base_url + "/api/method/smart_invoice_api.api.select_codes", data=data, headers=headers)

    response_json = r.json()
    data = response_json.get("message", response_json)
    if r.status_code != 200:
        frappe.msgprint(data)
        

    return data

@frappe.whitelist()
def run_test():   
    print("run_test")
    

    codes = get_codes()

    frappe.errprint(codes)
    frappe.msgprint("Connection Successful")
    
    return codes