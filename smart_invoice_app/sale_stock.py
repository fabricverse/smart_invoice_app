
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

def create_credit_note_payload(invoice, branch):
    company = self.env.company
    payload = {
        "tpin": company.tpin,
        "bhfId": company.bhf_id,
        "orgInvcNo": 78687,
        "cisInvcNo": "SAP000019",
        "custTin": "0782229123",
        "custNm": "Test Customer",
        "salesTyCd": "N",
        "rcptTyCd": "R",
        "pmtTyCd": "01",
        "salesSttsCd": "02",
        "cfmDt": "20240502102010",
        "salesDt": "20240502",
        "stockRlsDt": None,
        "cnclReqDt": None,
        "cnclDt": None,
        "rfdDt": None,
        "rfdRsnCd": "01",
        "totItemCnt": 1,
        "taxblAmtA": 86.2069,
        "taxblAmtB": 0.0,
        "taxblAmtC": 0.0,
        "taxblAmtC1": 0.0,
        "taxblAmtC2": 0.0,
        "taxblAmtC3": 0.0,
        "taxblAmtD": 0.0,
        "taxblAmtRvat": 0.0,
        "taxblAmtE": 0.0,
        "taxblAmtF": 0.0,
        "taxblAmtIpl1": 0,
        "taxblAmtIpl2": 0.0,
        "taxblAmtTl": 0,
        "taxblAmtEcm": 0,
        "taxblAmtExeeg": 0.0,
        "taxblAmtTot": 0.0,
        "taxRtA": 16,
        "taxRtB": 16,
        "taxRtC1": 0,
        "taxRtC2": 0,
        "taxRtC3": 0,
        "taxRtD": 0,
        "taxRtRvat": 16,
        "taxRtE": 0,
        "taxRtF": 10,
        "taxRtIpl1": 5,
        "taxRtIpl2": 0,
        "taxRtTl": 1.5,
        "taxRtEcm": 5,
        "taxRtExeeg": 3,
        "taxRtTot": 0,
        "taxAmtA": 13.7931,
        "taxAmtB": 0.0,
        "taxAmtC": 0.0,
        "taxAmtC1": 0.0,
        "taxAmtC2": 0.0,
        "taxAmtC3": 0.0,
        "taxAmtD": 0.0,
        "taxAmtRvat": 0.0,
        "taxAmtE": 0.0,
        "taxAmtF": 0,
        "taxAmtIpl1": 0,
        "taxAmtIpl2": 0.0,
        "taxAmtTl": 0,
        "taxAmtEcm": 0.0,
        "taxAmtExeeg": 0.0,
        "taxAmtTot": 0.0,
        "totTaxblAmt": 86.2069,
        "totTaxAmt": 13.7931,
        "totAmt": 100,
        "prchrAcptcYn": "N",
        "remark": "",
        "regrId": "admin",
        "regrNm": "admin",
        "modrId": "admin",
        "modrNm": "admin",
        "saleCtyCd": "1",
        "lpoNumber": "ZM2379729723",
        "currencyTyCd": "ZMW",
        "exchangeRt": "1",
        "destnCountryCd": "",
        "dbtRsnCd": "",
        "invcAdjustReason": "",
        "itemList": [
            {
                "itemSeq": 1,
                "itemCd": "20044",
                "itemClsCd": "50102517",
                "itemNm": "Chicken Wings",
                "bcd": "",
                "pkgUnitCd": "BA",
                "pkg": 0.0,
                "qtyUnitCd": "BE",
                "qty": 1.0,
                "prc": 100.0,
                "splyAmt": 100.0,
                "dcRt": 0.0,
                "dcAmt": 0.0,
                "isrccCd": "",
                "isrccNm": "",
                "isrcRt": 0.0,
                "isrcAmt": 0.0,
                "vatCatCd": "A",
                "exciseTxCatCd": None,
                "vatTaxblAmt": 86.2069,
                "exciseTaxblAmt": 0,
                "vatAmt": 13.7931,
                "exciseTxAmt": 0,
                "totAmt": 100
            }
        ]
    }
    return payload