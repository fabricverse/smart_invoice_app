import frappe

def check_phone_duplicates(doc, method=None):
    if not doc.mobile_no:
        frappe.throw(title="Mobile Number is Required", msg="Smart Invoice requires a phone numbers for customers.")
    else:
        customers = frappe.get_all('Customer', filters={'mobile_no': doc.mobile_no}, fields=['name', 'mobile_no'])
        for customer in customers:
            if len(customers) > 0 and (customer.mobile_no == doc.mobile_no and customer.name != doc.name):
                customer_doc = frappe.get_doc('Customer', customer.name)
                frappe.throw(title="Duplicate Mobile Number", msg=f"<a href='{customer_doc.get_url()}'><strong>{customer.name}</strong></a> is already using mobile number <strong>{doc.mobile_no}</strong>. Smart Invoice requires unique customer phone numbers.")
