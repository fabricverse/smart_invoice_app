# Copyright (c) 2024, Bantoo and Partners and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today
from smart_invoice_api.api import update_import_items as api_update_import_items

from smart_invoice_app.app import (
    api_date_format,
    format_date_only,
    get_doc_user_data,
    get_industry_tax_type,
    get_settings,
    get_tax_template_by_tax_code,
    get_uom_by_zra_unit,
    get_user_branch,
    set_defaults_exception,
)


class ASYCUDAVerification(Document):
    def validate(self):
        self.this_update_import_items()

    def on_update(self):
        self.get_purchase_items()

    @frappe.whitelist()
    def create_purchase_invoice(self, supplier):
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
        currency = (
            max(currencies.items(), key=lambda x: x[1])[0] if currencies else None
        )
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
        doc.update(
            {
                "supplier": supplier,
                "currency": currency,
                "conversion_rate": conversion_rate,
                "custom_asycuda": 1,
                "update_stock": 1,
                "custom_branch": branch,
                "items": items,
            }
        )
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert()

        for item in items:
            for i in self.items:
                if item.get("docname") == i.name:
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
            if (
                item.accepted != "Yes"
                or item.status_code in ["New", "Rejected"]
                or not item.item_class
            ):
                continue

            try:
                # This calls the method to match/create the ERPNext Item
                item_data = self.get_or_create_new_item(item)
                items.append(item_data)
            except Exception as e:
                frappe.msgprint(
                    f"Failed to create item <strong>{item.item_name}</strong>: {str(e)}"
                )

        return items

    def this_update_import_items(self):
        """Updates the status of ASYCUDA items on Smart Invoice"""

        branch = self.branch_code
        tpin = self.tpin

        items = []
        tasks = {item.task_code: item for item in self.items if item.accepted}

        for task in tasks:
            task_key = (branch, tasks[task].task_code, tasks[task].declaration_date)
            request_data = {
                "bhfId": branch,
                "tpin": tpin,
                "taskCd": tasks[task].task_code,
                "dclDe": api_date_format(tasks[task].declaration_date, date_only=True),
                "importItemList": [],
            }

            count = 0
            task_items = []

            for item in self.items:
                item_key = (branch, item.task_code, item.declaration_date)
                if task_key == item_key:  # ensure item belongs to a task
                    if (
                        item.accepted and item.status_code == "New"
                    ):  # ensure hasnt been updated to the api and and has been updated by the user
                        count += 1
                        content = {
                            "itemSeq": item.item_sequence,
                            "itemCd": item.item_name,
                            "hsCd": item.hs_code,
                            "itemClsCd": item.item_class,
                            "itemNm": item.item_name,
                            "imptItemSttsCd": get_status_code(item.accepted),
                        }
                        content.update(get_doc_user_data(self))
                        task_items.append(content)

            if count > 0:
                request_data.update({"importItemList": task_items})

                meta = {
                    "function": get_function_name(),
                    "doctype": self.doctype,
                    "entry": self.name,
                    "creator": self.owner,
                    "modifier": self.modified_by,
                }
                api_update_import_items(request_data, meta)

    def finish_importing_items(self, request_doc):
        """Initiates update of items.status_code
        Called by Sync Request > app.after_sync_process function
        @params:
            request_doc: The sync request doc that triggered this function
        """

        data = json.loads(request_doc.response)

        # --- TESTING BLOCK ---
        USE_MOCK = False  # Flip this to False when you have API access
        if USE_MOCK:
            # Simulate a successful API response
            data = get_mock_response()
            # We wrap it in a mock response object to mimic the real 'api' return
            request_doc = {"response": json.dumps(data)}
        if data:
            if data.get("resultCd") == "000":
                self.verify_item_status(request_doc)

    def verify_item_status(self, request_doc):
        """Get import items again and pass them to update_item_status to complete verification and updating of the doc
        An intermediate function passing latest asycuda status to update_item_status from app.after_sync_process triggered by update of sync_request doc on success
        """
        get_import_items(function="update_item_status", request_doc=request_doc)

    def trigger_reload(self, doc, name=None):
        frappe.publish_realtime(
            event="smart_invoice_event",
            message={
                "type": "reload",
                "name": name or doc.name,
                "doctype": doc.doctype,  # <-- REQUIRED for the list view match check
            },
            user=doc.modifier,
        )

    def update_item_status(self, request_doc):
        """Checks whether item has updated on smart invoice and updates it in the doc
        Called by update event in Sync Request -> app.after_sync_process
        """
        rs = json.loads(request_doc.response)

        # Use this to simulate the 'rs' variable in update_item_status
        # rs = {
        #     "resultCd": "000",
        #     "resultMsg": "It is succeeded",
        #     "data": {
        #         "itemList": [
        #             # Record 1 Should be removed from this list because processing is finished
        #             # {
        #             #     "taskCd": "810000591",
        #             #     "hsCd": "58071005",
        #             #     "itemNm": "EPSON PROJECTOR",
        #             #     "qty": 100,
        #             #     "imptItemsttsCd": "2"
        #             # }
        #         ]
        #     }
        # }

        if not rs or rs.get("resultCd") not in ["000", "001"]:
            return

        # Extract API data safely
        api_response_data = rs.get("data", {})
        item_data = api_response_data.get("itemList") or []

        # If API is empty, it usually means items were processed/cleared
        if not item_data:
            for item in self.items:
                # Only update if not already finalized
                if item.status_code not in ["Accepted", "Rejected"]:
                    self.set_status(item)
            frappe.db.commit()
            return

        db_dict = self.items_as_dict()

        # Build a lookup set of items currently "active" in the API
        # Note: We exclude status from the key so we can find the item regardless of its status change
        api_item_keys = set()
        for api_item in item_data:
            key = (
                api_item.get("taskCd"),
                api_item.get("hsCd"),
                api_item.get("itemNm"),
                flt(api_item.get("qty")),
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
        frappe.db.commit()

    def set_status(self, item):
        new_status = None
        if item.accepted == "Yes":
            new_status = "Accepted"
        elif item.accepted == "No":
            new_status = "Rejected"

        if new_status and item.status_code != new_status:
            # This updates the DB directly and updates the local object in memory
            item.db_set("status_code", new_status)

    def items_as_dict(self):
        return {
            (
                item.task_code,
                item.hs_code,
                item.item_name,
                item.qty,
                item.amount,
                item.status_code,
            ): item
            for item in reversed(self.items)
            if item.task_code
        }

    def get_zra_item_code(self, item):
        pass

    def get_or_create_new_item(self, item):
        settings = get_settings(self.company)
        if not settings.branches_setup:
            set_defaults_exception()

        price = flt(float(item.amount) / float(item.qty), 4)
        docname = item.name
        qty = flt(item.qty) or 1.0
        name = item.item_name

        custom_industry_tax_type, tax_code = get_industry_tax_type(
            tax_code=settings.item_tax_code
        )  #
        itt = get_tax_template_by_tax_code(settings.item_tax_code)  #
        uom = get_uom_by_zra_unit(item.qty_unit) or settings.default_uom

        # FIX: Parameterized SQL to prevent injection
        db_item = frappe.db.sql(
            """
            SELECT i.name as docname, i.item_code as item_code, i.item_name as item_name,
                   t.item_tax_template as item_tax_template, i.stock_uom as uom
            FROM tabItem as i
            LEFT JOIN `tabItem Tax` as t ON i.name = t.parent
            WHERE i.item_code = %s OR LOWER(i.item_name) = %s OR LOWER(i.item_code) = %s OR LOWER(i.item_name) = %s
        """,
            (name, name.lower(), name.lower(), name.lower()),
            as_dict=1,
        )

        maintain_stock = (
            1 if (item.status_code == "Accepted" or item.accepted == "Yes") else 0
        )

        if db_item:
            return {
                "item_code": db_item[0].item_code,
                "item_name": db_item[0].item_name,
                "item_tax_template": itt,
                "uom": uom,
                "qty": qty,
                "rate": price,
                "amount": float(item.amount),
                "docname": docname,
            }
        else:
            new = frappe.new_doc("Item")
            new.item_code = name
            new.item_name = name

            new.is_stock_item = maintain_stock
            new.valuation_rate = price
            new.item_group = "Products"
            new.custom_item_cls = item.item_class or settings.default_item_class
            new.country_of_origin = get_country_code(item.country_of_origin) or "Zambia"
            new.stock_uom = uom
            new.custom_pkg_unit = (
                get_uom_by_zra_unit(item.package_unit) or settings.default_packing_unit
            )

            new.custom_industry_tax_type = custom_industry_tax_type

            new.append("taxes", {"doctype": "Item Tax", "item_tax_template": itt})

            new.insert(ignore_permissions=True)

            return {
                "item_code": new.item_code,
                "item_name": new.item_name,
                "item_tax_template": itt,
                "uom": new.stock_uom,
                "qty": item.qty,
                "rate": price,
                "amount": float(item.amount),
                "docname": docname,
            }


def get_mock_response(scenario="SUCCESS"):
    """Returns a fake API response dictionary"""
    if scenario == "SUCCESS":
        return {
            "resultCd": "000",
            "resultMsg": "Transaction Successful",
            "data": {
                "itemList": [
                    # {
                    #     "taskCd": "TASK-101", "dclDe": "20240101", "itemSeq": 1,
                    #     "hsCd": "1234", "itemNm": "MOCK ITEM A", "imptItemsttsCd": "2",
                    #     "qty": 10, "invcFcurAmt": 1000, "invcFcurCd": "ZMW", "invcFcurExcrt": 1.0
                    # }
                    {
                        "taskCd": "810000591",
                        "dclDe": "20240812",
                        "itemSeq": 1,
                        "dclNo": "C 76937-2024-KZU",
                        "hsCd": "58071005",
                        "itemNm": "EPSON PROJECTOR",
                        "imptItemsttsCd": "2",
                        "orgnNatCd": "ZA",
                        "exptNatCd": "ZA",
                        "pkg": 1,
                        "pkgUnitCd": "PK",
                        "qty": 100,
                        "qtyUnitCd": "GRO",
                        "totWt": 6.7,
                        "netWt": 6.7,
                        "spplrNm": None,
                        "agntNm": "UNI 4",
                        "invcFcurAmt": 3171.36,
                        "invcFcurCd": "ZAR",
                        "invcFcurExcrt": 1.17,
                        "dclRefNum": None,
                    }
                ]
            },
        }
    else:
        return {
            "resultCd": "999",
            "resultMsg": "Internal Provider Error",
            "data": {"itemList": []},
        }


def get_country_code(code):
    temp = frappe.get_all("Country", filters={"code": code}, fields=["country_name"])
    name = None
    if temp:
        name = temp[0].country_name
    return name


def get_status_by_code(code):
    statuses = {"3": "Accepted", "4": "Rejected"}
    return statuses.get(code, "New")


def get_status_code(status):
    codes = {"New": "2", "Accepted": "3", "Rejected": "4", "Yes": "3", "No": "4"}
    return codes.get(status, "2")


import inspect


def get_function_name():
    """Returns the name of the caller function."""
    return inspect.stack()[1].function


def get_selected_branch():
    """Returns the selected branch from cache.

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
            "company": company,
        }
    else:
        return None


from smart_invoice_api.api import select_import_items as api_select_import_items


@frappe.whitelist()
def get_import_items(from_list=False, function=None, request_doc=None):
    """Starts the process of creating import items from Smart Invoice.
    Called from List without function and request_doc defined but from_list=False.
    Or called from verify_item_status with both defined, without from_list
    """

    request = None
    branch_data = None
    data = {}

    meta = {"function": function, "doctype": "ASYCUDA Verification"}
    if request_doc:
        # called by verify_item_status
        meta.update(
            {
                "entry": request_doc.entry,
                "creator": request_doc.creator,
                "modifier": request_doc.modifier,
                "doctype": request_doc.type,
            }
        )

        # use original tpin and branch code from request doc
        request = json.loads(request_doc.request)
        data.update(
            {"bhf_id": request.get("bhfId", "000"), "tpin": request.get("tpin")}
        )
    else:
        # called by list, getting branch details from user session
        branch_data = get_selected_branch()
        data.update(
            {"bhf_id": branch_data.get("branch_code"), "tpin": branch_data.get("tpin")}
        )

        meta.update({"function": get_function_name()})

    api_select_import_items(data, initialize=True, meta=meta)


def finish_get_import_items(request, from_list=False):
    """Completes the process of creating import items from Smart Invoice by processing the API response.
    Called after receiving API response via Sync Request -> app.py -> after_sync_process
    Receives Sync Request doc
    """
    try:
        data = json.loads(request.response)
        create_imports(request, data, from_list)
    except Exception as e:
        notify_user(request, f"Failed to parse API response: {str(e)}", indicator="Red")


def notify_user(doc, message, indicator):
    """Pushes a final completion event to trigger form reload on the frontend."""
    frappe.publish_realtime(
        event="smart_invoice_event",
        message={
            "status": doc.status,
            "message": message,
            "indicator": indicator,
            "name": doc.entry,
            "doctype": doc.type,
            "type": "progress",
        },
        user=doc.modifier,
        doctype=doc.type,
        docname=doc.entry,
    )


def prints(data):
    frappe.publish_realtime(
        event="smart_invoice_event",
        message={
            "message": data,
            "indicator": "print",
            "name": "print",
            "type": "print",
        },
        user=frappe.session.user,
    )


def clean_branch_name(name, tpin):
    if not name or not tpin:
        return name
    return name.replace(f" - {tpin}", "").strip()


def shorten_company_name(name):
    """return first word in company name string"""
    return name.split()[0] if name else name


def no_new_items_msg(request, company_name, branch_name):
    notify_user(
        request,
        f"{company_name}'s <b>{branch_name}</b> branch has no imports",
        indicator="blue",
    )


def create_imports(request, data, from_list):
    branch_details = get_branch_details_from_request(request)
    c_branch_name = clean_branch_name(
        branch_details.get("branch_name"), branch_details.get("tpin")
    ) or branch_details.get("branch_name")

    company_short_name = shorten_company_name(branch_details.get("company"))

    if data and data.get("resultCd", False) == "000":
        items = data.get("data", {"itemList": None}).get("itemList")
        if not items or len(items) == 0:
            no_new_items_msg(request, company_short_name, c_branch_name)
            return
        create_doc(request, items)
    else:
        no_new_items_msg(request, company_short_name, c_branch_name)


def create_doc(request, item_data):
    """Processes incoming item data, filters out existing duplicates,
    and creates new ASYCUDA Verification documents cleanly grouped by currency.
    """

    # item_data = [{'taskCd': '810000591', 'dclDe': '20240812', 'itemSeq': 1, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'EPSON PROJECTOR', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'USD', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000592', 'dclDe': '20240812', 'itemSeq': 2, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'DELL DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000593', 'dclDe': '20240812', 'itemSeq': 3, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'HP DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZMW', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000594', 'dclDe': '20240812', 'itemSeq': 4, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'IPHONE 14 DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZMW', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000595', 'dclDe': '20240812', 'itemSeq': 5, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'EPSON PROJECTOR', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000596', 'dclDe': '20240812', 'itemSeq': 6, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'DELL DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000597', 'dclDe': '20240812', 'itemSeq': 7, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'HP DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}, {'taskCd': '810000598', 'dclDe': '20240812', 'itemSeq': 8, 'dclNo': 'C 76937-2024-KZU', 'hsCd': '58071005', 'itemNm': 'IPHONE 14 DESKTOPS', 'imptItemsttsCd': '2', 'orgnNatCd': 'ZA', 'exptNatCd': 'ZA', 'pkg': 1, 'pkgUnitCd': 'PK', 'qty': 100, 'qtyUnitCd': 'GRO', 'totWt': 6.7, 'netWt': 6.7, 'spplrNm': None, 'agntNm': 'UNI 4', 'invcFcurAmt': 3171.36, 'invcFcurCd': 'ZAR', 'invcFcurExcrt': 1.17, 'dclRefNum': None}]

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
        """,
        as_dict=1,
    )

    db_dict = {
        (
            item.task_code,
            item.hs_code,
            item.item_name,
            item.qty,
            item.amount,
            item.status_code,
        ): item
        for item in reversed(db_items)
        if item.task_code
    }

    # Clean dictionary grouping structure
    currency_groups = {}

    for item in item_data:
        task_code = item.get("taskCd", None)
        declaration_date = item.get("dclDe", today())
        declaration_number = item.get("dclNo", None)
        declaration_reference = item.get("dclRefNum", None)
        hs_code = item.get("hsCd", None)
        item_name = item.get("itemNm", None)
        country_of_origin = item.get("orgnNatCd", None)
        export_code = item.get("exptNatCd", None)
        number_of_packages = item.get("pkg", None)
        package_unit = item.get("pkgUnitCd", None)
        qty_unit = item.get("qtyUnitCd", None)
        total_weight = item.get("totWt", None)
        net_weight = item.get("netWt", None)
        supplier = item.get("spplrNm", None)
        agent_name = item.get("agntNm", None)
        exchange_rate = item.get("invcFcurExcrt", None)
        status_code = item.get("imptItemsttsCd", None)
        item_sequence = item.get("itemSeq", None)

        # CRITICAL: Force strictly isolated conversions per item
        current_qty = float(item.get("qty", 0) or 0)
        current_amount = float(item.get("invcFcurAmt", 0) or 0)
        currency_code = item.get("invcFcurCd", "Unknown")

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
                "total_amt": 0.0,
            }

        # Add values ONLY to this specific currency bucket
        currency_groups[currency_code]["total_qty"] += current_qty
        currency_groups[currency_code]["total_amt"] += current_amount

        currency_groups[currency_code]["items"].append(
            {
                "task_code": task_code,
                "declaration_date": format_date_only(declaration_date),
                "declaration_number": declaration_number,
                "declaration_reference": declaration_reference,
                "hs_code": hs_code,
                "item_name": item_name,
                "status_code": status,
                "country_of_origin": country_of_origin,
                "export_code": export_code,
                "number_of_packages": number_of_packages,
                "package_unit": package_unit,
                "qty": current_qty,
                "qty_unit": qty_unit,
                "total_weight": total_weight,
                "net_weight": net_weight,
                "supplier": supplier,
                "agent_name": agent_name,
                "amount": current_amount,
                "currency": currency_code,
                "exchange_rate": exchange_rate,
                "item_sequence": item_sequence,
            }
        )

    branch_details = get_branch_details_from_request(request)

    # Process each currency group into its own separate document
    if currency_groups:
        for currency, data in currency_groups.items():
            doc = frappe.new_doc("ASYCUDA Verification")
            doc.update(
                {
                    "company": branch_details.get("company"),
                    "branch": branch_details.get("branch_name"),
                    "items": data["items"],
                    "total_qty": data["total_qty"],
                    "total_amt": data[
                        "total_amt"
                    ],  # Now 100% localized to this loop currency
                    "currency": currency,
                }
            )
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

        branch_data = frappe.db.get_values(
            "Branch",
            {"custom_bhf_id": branch, "custom_tpin": tpin},
            ["custom_company", "name"],
            as_dict=True,
            cache=True,
        )

        return {
            "branch": branch,
            "branch_name": branch_data[0].name,
            "tpin": tpin,
            "company": branch_data[0].custom_company,
        }
    except (json.JSONDecodeError, TypeError):
        return None
