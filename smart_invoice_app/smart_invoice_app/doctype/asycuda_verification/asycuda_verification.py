# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import frappe, json
from frappe.model.document import Document
from smart_invoice_app.app import (api, validate_api_response, 
    format_date_only, get_doc_user_data, api_date_format, 
    get_uom_by_zra_unit, get_industry_tax_type, get_tax_template_by_tax_code,
    get_user_branches)
from frappe.utils import today, flt

class ASYCUDAVerification(Document):
    def validate(self):
        self.update_import_items()

    def on_update(self):
        self.get_purchase_items()
            
    @frappe.whitelist()
    def create_purchase_invoice(self,supplier):
        return self.create_purchase_doc(supplier, "Purchase Invoice")

    @frappe.whitelist()
    def create_purchase_receipt(self, supplier):
        return self.create_purchase_doc(supplier, "Purchase Receipt")

    def get_currency_and_exchange_rate(self):
        # Create sets to store unique currencies and rates
        currencies = {}
        rates = {}
        
        # Count frequency of each currency and rate
        for item in self.items:
            if item.currency:
                currencies[item.currency] = currencies.get(item.currency, 0) + 1
            if item.exchange_rate:
                rates[item.exchange_rate] = rates.get(item.exchange_rate, 0) + 1
        
        # Get most common currency and rate (or None if no items)
        currency = max(currencies.items(), key=lambda x: x[1])[0] if currencies else None
        rate = max(rates.items(), key=lambda x: x[1])[0] if rates else None

        return currency, rate


    def create_purchase_doc(self, supplier, doctype):
        
        items = self.get_purchase_items()
        if not items:
            frappe.throw("No items to add. You need to update import items first")

        currency, conversion_rate = self.get_currency_and_exchange_rate()

        selected_branch = get_selected_branch()
        branch = selected_branch.get("branch_code") if selected_branch else "000"

        doc = frappe.new_doc(doctype)        
        doc.update({
            "supplier": supplier,
            "currency": currency,
            "conversion_rate": conversion_rate,
            "custom_asycuda": 1,
            "update_stock": 1,
            "custom_branch": branch,
            "items": items
        })
        doc.flags.ignore_permissions=True
        doc.flags.ignore_mandatory=True
        doc.insert()

        for item in items:
            for i in self.items:
                if item.get('docname') == i.name:
                    if doctype == "Purchase Invoice":
                        i.purchase_invoice = doc.name
                    else: 
                        i.purchase_receipt = doc.name
        self.save()
        return doc.name
    
    @frappe.whitelist()
    def get_purchase_items(self):
        items = []
        for item in self.items:
            # If you want to ALLOW "New" items, remove this block.
            # If you only want "Accepted" items, keep it but check against "Accepted".
            
            # Change: Only skip if it is specifically Rejected or empty
            if not item.accepted or (not item.status_code or item.status_code == "Rejected"):
                continue
                
            try:
                # This calls the method to match/create the ERPNext Item
                item_data = self.get_or_create_new_item(item)
                items.append(item_data)
            except Exception as e:
                frappe.msgprint(f"Failed to create item <strong>{item.item_name}</strong>: {str(e)}")
                
        return items
            

    def update_import_items(self):
        """ Updates the status of ASYCUDA items on Smart Invoice """

        selected_branch = get_selected_branch()
        
        items = []
        tasks = {
            item.task_code: item 
            for item in self.items 
            if item.accepted                    
        }

        for task in tasks:
            # TODO: Using fixed branch code "000" for now, but this can be dynamic based on user or company settings
            task_key = (current_branch, tasks[task].task_code,  tasks[task].declaration_date)
            request_data = {
                "bhfId": current_branch or "000",
                "taskCd":  tasks[task].task_code,
                "dclDe": api_date_format( tasks[task].declaration_date, date_only=True),
                "importItemList": []
            }

            count = 0
            task_items = []

            for item in self.items:
                item_key = (current_branch or "000", item.task_code, item.declaration_date)
                if task_key == item_key: # ensure item belongs to a task 
                    if item.accepted and item.status_code == "New": # ensure hasnt been updated to the api and and has been updated by the user
                        count+=1
                        content = {
                            "itemSeq": item.item_sequence,
                            "itemCd": item.item_name,
                            "hsCd": item.hs_code,
                            "itemClsCd": item.item_class,
                            "itemNm": item.item_name,
                            "imptItemSttsCd": get_status_code(item.accepted)
                        }
                        content.update( get_doc_user_data(self) )
                        task_items.append(content)

            if count > 0:
                request_data.update({"importItemList": task_items})
                
                # --- TESTING BLOCK ---
                USE_MOCK = True  # Flip this to False when you have API access
                if USE_MOCK:
                    # Simulate a successful API response
                    response_data = get_mock_response() #"SUCCESS") 
                    # We wrap it in a mock response object to mimic the real 'api' return
                    response = {"response": json.dumps(response_data)}
                    print(request_data)
                else:
                    # REAL API CALL
                    response = api("/api/method/smart_invoice_api.api.update_import_items", request_data)
                # --- END TESTING BLOCK ---

                # response = api( "/api/method/smart_invoice_api.api.update_import_items", request_data )
                validate_api_response(response)
                response_data = json.loads(response.get('response'))
                
                if response_data:  
                    result_code = response_data.get("resultCd")                  
                    if response_data.get("resultCd") =="000":
                        self.update_item_status()   
                        frappe.msgprint(f"Smart Invoice: {response_data.get('resultMsg')}", indicator='Success', alert=True)
                    if response_data.get("resultCd") == "001":
                        frappe.msgprint(f"Smart Invoice: {response_data.get('resultMsg')}", indicator='Warn', alert=True)
                    else:
                        frappe.msgprint(f"Cannot connect to Smart Invoice ({result_code}). Please try again later.", indicator="Red", alert=True)

    
    def update_item_status(self):

        rs = select_import_items()
        # Use this to simulate the 'rs' variable in update_item_status
        # rs = {
        #     "resultCd": "000",
        #     "resultMsg": "It is succeeded",
        #     "data": {
        #         "itemList": [
        #             # Record 1 (LG TV) is GONE from this list because processing is finished
        #             {
        #                 "taskCd": "84013245",
        #                 "hsCd": "58071005",
        #                 "itemNm": "ZEN OFFICE CHAIR",
        #                 "qty": 100,
        #                 "imptItemsttsCd": "2" 
        #             },
        #             {
        #                 "taskCd": "84013245",
        #                 "hsCd": "48191007",
        #                 "itemNm": "HONDA GENSET",
        #                 "qty": 100,
        #                 "imptItemsttsCd": "2"
        #             }
        #         ]
        #     }
        # }

        if not rs or rs.get('resultCd') not in ["000", "001"]:
            return

        # Extract API data safely
        api_response_data = rs.get('data', {})
        item_data = api_response_data.get('itemList') or []

        # If API is empty, it usually means items were processed/cleared
        if not item_data:
            for item in self.items:
                # Only update if not already finalized
                if item.status_code not in ["Accepted", "Rejected"]:
                    self.set_status(item)
            # self.save()
            return

        db_dict = self.items_as_dict()

        # Build a lookup set of items currently "active" in the API
        # Note: We exclude status from the key so we can find the item regardless of its status change
        api_item_keys = set()
        for api_item in item_data:
            key = (
                api_item.get('taskCd'),
                api_item.get('hsCd'),
                api_item.get('itemNm'),
                flt(api_item.get('qty'))
            )
            api_item_keys.add(key)

        # Iterate local items and update status if they are no longer in the API queue
        for item in self.items:
            local_key = (item.task_code, item.hs_code, item.item_name, flt(item.qty))
            
            if local_key not in api_item_keys:
                # Item is no longer in the "Pending" API list, 
                # so we sync it to its "Accepted/Rejected" state
                if item.status_code not in ["Accepted", "Rejected"]:
                    self.set_status(item)
        
        # self.save()
                

    def set_status(self, item):
        if item.accepted == "Yes":
            item.status_code = "Accepted"
        elif item.accepted == "No":
            item.status_code = "Rejected"

    def items_as_dict(self):
        return {
            (item.task_code, item.hs_code, item.item_name, item.qty, item.amount, item.status_code): item 
            for item in reversed(self.items)
            if item.task_code
        }

    def get_zra_item_code(self, item):
        pass

    def get_or_create_new_item(self, item):
        company_name = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value('Global Defaults', 'default_company')
        company = frappe.get_cached_doc("Company", company_name)

        price = flt(float(item.amount)/float(item.qty), 4)
        docname = item.name
        qty = flt(item.qty) or 1.0
        name = item.item_name

        custom_industry_tax_type, tax_code = get_industry_tax_type(tax_code=company.custom_tax_code) #
        itt = get_tax_template_by_tax_code(company.custom_tax_code) #
        uom = get_uom_by_zra_unit(item.qty_unit) or company.custom_default_unit_of_measure

        # FIX: Parameterized SQL to prevent injection
        db_item = frappe.db.sql("""
            SELECT i.name as docname, i.item_code as item_code, i.item_name as item_name, 
                   t.item_tax_template as item_tax_template, i.stock_uom as uom
            FROM tabItem as i
            LEFT JOIN `tabItem Tax` as t ON i.name = t.parent
            WHERE i.item_code = %s OR LOWER(i.item_name) = %s OR LOWER(i.item_code) = %s OR LOWER(i.item_name) = %s
        """, (name, name.lower(), name.lower(), name.lower()), as_dict=1)

        if db_item:
            return {
                'item_code': db_item[0].item_code,
                'item_name': db_item[0].item_name,
                'item_tax_template': itt,
                'uom': uom,
                'qty': qty,
                'rate': price,
                'amount': float(item.amount),
                'docname': docname
            }
        else:
            new = frappe.new_doc("Item")
            new.item_code = name
            new.item_name = name

            new.is_stock_item = 1 if item.status_code == "Accepted" else 0
            new.valuation_rate = price
            new.item_group = "Products"
            new.custom_item_cls = item.item_class or company.custom_default_item_class
            new.country_of_origin = get_country_code(item.country_of_origin) or "Zambia"
            new.stock_uom = uom
            new.custom_pkg_unit = get_uom_by_zra_unit(item.package_unit) or company.custom_packaging_unit

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
                'uom': new.stock_uom,
                'qty': item.qty,
                'rate': price,
                'amount': float(item.amount),
                'docname': docname
            }
def get_mock_response(scenario="SUCCESS"):
    """Returns a fake API response dictionary"""
    if scenario == "SUCCESS":
        return {
            "resultCd": "000",
            "resultMsg": "Transaction Successful",
            "data": {
                "itemList": [
                    {
                        "taskCd": "TASK-101", "dclDe": "20240101", "itemSeq": 1,
                        "hsCd": "1234", "itemNm": "MOCK ITEM A", "imptItemsttsCd": "2",
                        "qty": 10, "invcFcurAmt": 1000, "invcFcurCd": "ZMW", "invcFcurExcrt": 1.0
                    }
                ]
            }
        }
    else:
        return {
            "resultCd": "999",
            "resultMsg": "Internal Provider Error",
            "data": {"itemList": []}
        }


def get_country_code(code):
    temp = frappe.get_all("Country", filters={"code": code}, fields=["country_name"])
    name = None
    if temp:
        name = temp[0].country_name
    return name

def get_status_by_code(code):
    statuses = {
        "3": "Accepted",
        "4": "Rejected"
    }
    return statuses.get(code, "New")


def get_status_code(status):
    codes = {
        "New": "2",
        "Accepted": "3",
        "Rejected": "4",
        "Yes": "3",
        "No": "4"
    }
    return codes.get(status, "2")

import inspect
def get_function_name():
    """Returns the name of the caller function."""
    return inspect.stack()[1].function

def get_selected_branch():
    """ Returns the selected branch from cache. 
    
        Return:
           dict: branch, branch_name, tpin
    """
    user = frappe.session.user
    if user:
        branch_code = frappe.cache.hget(f"session_branch:{user}", "branch_code")
        branch_doc_name = frappe.cache.hget(f"session_branch:{user}", "branch_doc_name")
        tpin = frappe.cache.hget(f"session_branch:{user}", "tpin")
        company = frappe.cache.hget(f"session_branch:{user}", "company")
    return {
        "branch_code": branch_code,
        "branch_doc_name": branch_doc_name,
        "tpin": tpin,
        "company": company
    }

from smart_invoice_api.api import select_import_items as api_select_import_items
@frappe.whitelist()
def get_import_items(from_list=False):
    """ Starts the process of creating import items from Smart Invoice. Called from List """
    branch_data = get_selected_branch()
    data={
        "bhf_id": branch_data.get("branch_code"), 
        "tpin": branch_data.get("tpin")
    }

    api_select_import_items(data, initialize=True, meta={
        "function": get_function_name(), "doctype": "Asycuda Verification"
    })

def finish_get_import_items(request, from_list=False):
    """ Completes the process of creating import items from Smart Invoice by processing the API response. 
    Called after receiving API response via Sync Request -> app.py -> after_sync_process
    Receives Sync Request doc
    """
    response = request.response
    try:
        data = json.loads(response)
    except Exception as e:
        notify_user(request, f"Failed to parse API response: {str(e)}", indicator="Red")

    create_imports(request, data, from_list)

def notify_user(doc, message, indicator):
    """Pushes a final completion event to trigger form reload on the frontend."""
    frappe.publish_realtime(
        event="sync_progress",
        message={
            "status": doc.status,
            "message": message,
            "indicator": indicator,
            "name": doc.name
        },
        user=doc.modifier,
        doctype=doc.type,
        docname=doc.entry
    )

def clean_branch_name(name, tpin):
    if not name or not tpin:
        return name
    return name.replace(f" - {tpin}", "").strip()

def shorten_company_name(name):
    """ return first word in company name string """
    return name.split()[0] if name else name
    

def no_new_items_msg(request, company_name, branch_name):
    notify_user(request, f"{company_name}'s <b>{branch_name}</b> branch has no imports", indicator="blue")
    
def create_imports(request, data, from_list):  
    branch_details = get_branch_details_from_request(request)

    c_branch_name = clean_branch_name(branch_details.get("branch_name"), branch_details.get("tpin")) or branch_details.get("branch_name")
    
    company_short_name = shorten_company_name(branch_details.get("company"))

    if data and data.get('resultCd', False)=="000":
        items = data.get('data', {'itemList': None}).get('itemList')
        if not items or len(items) == 0:
            no_new_items_msg(request, company_short_name, c_branch_name)
            return
        create_doc(request, items)
    else:
        no_new_items_msg(request, company_short_name, c_branch_name)

"""
{
    'taskCd': '84013245', 'dclDe': '20241109', 'itemSeq': 1, 'dclNo': 'C 76937-2024-KZU', 
    'hsCd': '48195190', 
    'itemNm': 'TOYOTA HILUX', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 
    'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 1.01, 'netWt': 1.01, 'spplrNm': None, 
    'agntNm': 'CLEARING AGENTS LIMITED 1', 'invcFcurAmt': 10440, 'invcFcurCd': 'ZAR', 
    'invcFcurExcrt': 1.17, 'dclRefNum': None
}
"""

def create_doc(request, item_data):
    """Processes incoming item data, filters out existing duplicates, 
    and creates new ASYCUDA Verification documents cleanly grouped by currency.
    """
    
    item_data = [{'taskCd': '810000591', 'dclDe': '20240812', 'itemSeq': 1, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'EPSON PROJECTOR', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'USD', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000592', 'dclDe': '20240812', 'itemSeq': 2, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'DELL DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000593', 'dclDe': '20240812', 'itemSeq': 3, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'HP DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZMW', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000594', 'dclDe': '20240812', 'itemSeq': 4, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'IPHONE 14 DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZMW', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000595', 'dclDe': '20240812', 'itemSeq': 5, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'EPSON PROJECTOR', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000596', 'dclDe': '20240812', 'itemSeq': 6, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'DELL DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000597', 'dclDe': '20240812', 'itemSeq': 7, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'HP DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000598', 'dclDe': '20240812', 'itemSeq': 8, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'IPHONE 14 DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}]

    db_items = frappe.db.sql(
        """
            SELECT
                i.name as row_name, i.task_code, i.declaration_date, i.declaration_number,
                i.declaration_reference, i.hs_code, i.item_name, i.status_code,
                i.country_of_origin, i.export_code, i.number_of_packages, i.package_unit,
                i.qty, i.qty_unit, i.total_weight, i.net_weight, i.supplier,
                i.agent_name, i.amount, i.currency, i.exchange_rate, d.creation, d.name as docname
            FROM `tabASYCUDA Items` as i
            LEFT JOIN `tabASYCUDA Verification` as d ON d.name = i.parent
            ORDER BY d.creation DESC
        """, as_dict=1)

    db_dict = {
        (item.task_code, item.hs_code, item.item_name, item.qty, item.amount, item.status_code): item 
        for item in reversed(db_items)
        if item.task_code
    }

    # Clean dictionary grouping structure
    currency_groups = {}

    for item in item_data:        
        task_code = item.get('taskCd', None)
        declaration_date = item.get('dclDe', today())
        declaration_number = item.get('dclNo', None)
        declaration_reference = item.get('dclRefNum', None)
        hs_code = item.get('hsCd', None)
        item_name = item.get('itemNm', None)
        country_of_origin = item.get('orgnNatCd', None)
        export_code = item.get('exptNatCd', None)
        number_of_packages = item.get('pkg', None)
        package_unit = item.get('pkgUnitCd', None)
        qty_unit = item.get('qtyUnitCd', None)
        total_weight = item.get('totWt', None)
        net_weight = item.get('netWt', None)
        supplier = item.get('spplrNm', None)
        agent_name = item.get('agntNm', None)
        exchange_rate = item.get('invcFcurExcrt', None)
        status_code = item.get('imptItemsttsCd', None)
        item_sequence = item.get('itemSeq', None)

        # CRITICAL: Force strictly isolated conversions per item
        current_qty = float(item.get('qty', 0) or 0)
        current_amount = float(item.get('invcFcurAmt', 0) or 0)
        currency_code = item.get('invcFcurCd', "Unknown")

        status = get_status_by_code(status_code) or "New"

        item_key = (task_code, hs_code, item_name, current_qty, current_amount, status)
        
        # Skip existing records       
        if item_key in db_dict:
            continue

        # Initialize the currency block dynamically if it's the first time seeing it
        if currency_code not in currency_groups:
            currency_groups[currency_code] = {
                "items": [],
                "total_qty": 0.0,
                "total_amt": 0.0
            }

        # Add values ONLY to this specific currency bucket
        currency_groups[currency_code]["total_qty"] += current_qty
        currency_groups[currency_code]["total_amt"] += current_amount
        
        currency_groups[currency_code]["items"].append({
            'task_code': task_code,
            'declaration_date': format_date_only(declaration_date),
            'declaration_number': declaration_number,
            'declaration_reference': declaration_reference,
            'hs_code': hs_code,
            'item_name': item_name,
            'status_code': status,
            'country_of_origin': country_of_origin,
            'export_code': export_code,
            'number_of_packages': number_of_packages,
            'package_unit': package_unit,
            'qty': current_qty,
            'qty_unit': qty_unit,
            'total_weight': total_weight,
            'net_weight': net_weight,
            'supplier': supplier,
            'agent_name': agent_name,
            'amount': current_amount,
            'currency': currency_code,
            'exchange_rate': exchange_rate,
            'item_sequence': item_sequence
        })
    
    branch_details = get_branch_details_from_request(request)

    # Process each currency group into its own separate document
    if currency_groups:
        for currency, data in currency_groups.items():
            doc = frappe.new_doc("ASYCUDA Verification")
            doc.update({
                "company": branch_details.get("company"),
                "branch": branch_details.get("branch_name"),
                "items": data["items"],
                "total_qty": data["total_qty"],
                "total_amt": data["total_amt"], # Now 100% localized to this loop currency
                "currency": currency,
            })
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
            
        
        msg = f"Added {len(currency_groups)} new import document"
        if len(currency_groups) > 1:
            msg = f"Added {len(currency_groups)} new import documents"
        notify_user(request, msg, "green")
    else:
        company_short_name = shorten_company_name(branch_details.get("company"))
        no_new_items_msg(request, company_short_name, branch_details.get("branch_name"))

def get_branch_details_from_request(request):
    """Extracts and returns branch details (code, name, tpin, and company) from the incoming request payload."""
    if not request or not request.request:
        return None
        
    try:
        data = json.loads(request.request)
        branch = data.get("bhfId", "000")
        tpin = data.get("tpin")
        
        # Optimization 5: Cached string queries are fast, but ensure fields are indexed in DocType
        branch_data = frappe.db.get_values(
            "Branch", 
            {"custom_bhf_id": branch, "custom_tpin": tpin}, 
            ["custom_company", "name"],
            as_dict=True,
            cache=True
        )
        
        return {
            "branch": branch,
            "branch_name": branch_data[0].name,
            "tpin": tpin,
            "company": branch_data[0].custom_company
        }
    except (json.JSONDecodeError, TypeError):
        return None