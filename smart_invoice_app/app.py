import frappe
from datetime import datetime

"""global method to convert date to yyyymmddmmss"""
def api_date_format(date):
    if type(date) == str:
        date = datetime.strptime(date.split('.')[0], "%Y-%m-%d %H:%M:%S")
    elif type(date) != datetime:
        frappe.throw("Invalid date type")
    return date.strftime("%Y%m%d%H%M%S")

