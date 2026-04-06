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

        branches = get_user_branches()
        branch = branches[0].get('branch') if branches else "000"
        
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
        items = []

        tasks = {
            item.task_code: item 
            for item in self.items 
            if item.accepted                    
        }

        for task in tasks:

            task_key = ("000", tasks[task].task_code,  tasks[task].declaration_date)
            request_data = {
                "bhfId": "000",
                "taskCd":  tasks[task].task_code,
                "dclDe": api_date_format( tasks[task].declaration_date, date_only=True),
                "importItemList": []
            }

            count = 0
            task_items = []

            for item in self.items:
                item_key = ("000", item.task_code, item.declaration_date)
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
                    # break # TODO: remove

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

def select_import_items():
    response = api( "/api/method/smart_invoice_api.api.select_import_items", {
            "bhf_id": "000"
        }, 
        initialize=True,
    )
    validate_api_response(response)
    return json.loads(response.get('response'))

@frappe.whitelist()
def get(from_list=False):
    data = select_import_items()
    create_imports(data, from_list)
    return data

def create_imports(data, from_list):    
    if data and data.get('resultCd', False)=="000":
        items = data.get('data', {'itemList': None}).get('itemList')
        if not items:
            frappe.msgprint("No new imports", indicator="Blue", alert=True)
            return
        create_doc(items)
    else:
        if from_list:
            frappe.msgprint("No new imports", indicator="Blue", alert=True)
            return

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
def create_doc(item_data):
    items = []
    total_qty = 0
    
    db_items = frappe.db.sql(
        """
            SELECT
                i.name as row_name,
                i.task_code,
                i.declaration_date,
                i.declaration_number,
                i.declaration_reference,
                i.hs_code,
                i.item_name,
                i.status_code,
                i.country_of_origin,
                i.export_code,
                i.number_of_packages,
                i.package_unit,
                i.qty,
                i.qty_unit,
                i.total_weight,
                i.net_weight,
                i.supplier,
                i.agent_name,
                i.amount,
                i.currency,
                i.exchange_rate,
                d.creation,
                d.name as docname
            FROM `tabASYCUDA Items` as i
            LEFT JOIN `tabASYCUDA Verification` as d 
            ON d.name = i.parent
            ORDER BY d.creation DESC
            LIMIT 600
        """, as_dict=1)

    # db_dict = { (item.task_code, item.item_name, item.qty, item.amount): item for item in db_items }
    db_dict = {
        (item.task_code, item.hs_code, item.item_name, item.qty, item.amount, item.status_code): item 
        for item in reversed(db_items)
        if item.task_code
    }

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
        qty = float(item.get('qty', None))
        qty_unit = item.get('qtyUnitCd', None)
        total_weight = item.get('totWt', None)
        net_weight = item.get('netWt', None)
        supplier = item.get('spplrNm', None)
        agent_name = item.get('agntNm', None)
        amount = item.get('invcFcurAmt', None)
        currency = item.get('invcFcurCd', None)
        exchange_rate = item.get('invcFcurExcrt', None)
        status_code = item.get('imptItemsttsCd', None)
        item_sequence = item.get('itemSeq', None)

        status = get_status_by_code(status_code) or "New"
        qty = float(item.get('qty', None))
        total_qty += qty

        item_key = (task_code, hs_code, item_name, qty, amount, status)
        
        # skip existing records and continue to the next record       
        if item_key in db_dict:
            continue

        items.append({
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
            'qty': qty,
            'qty_unit': qty_unit,
            'total_weight': total_weight,
            'net_weight': net_weight,
            'supplier': supplier,
            'agent_name': agent_name,
            'amount': amount,
            'currency': currency,
            'exchange_rate': exchange_rate,
            'item_sequence': item_sequence
        })

    if items:
        doc = frappe.new_doc("ASYCUDA Verification")
        doc.update({
            "items": items,
            "total_qty": total_qty
        })
        
        doc.flags.ignore_permissions=True
        doc.insert(ignore_permissions=True)
    else:
        frappe.msgprint("Smart Invoice: No new imports", indicator="Blue", alert=True)