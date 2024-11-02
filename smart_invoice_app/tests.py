import unittest
from unittest.mock import patch, MagicMock
from apps.smart_invoice_app.smart_invoice_app.app import prepare_invoice_data

class TestPrepareInvoiceData(unittest.TestCase):

    @patch('frappe.get_doc')
    @patch('frappe.get_cached_doc')
    @patch('frappe.throw')
    def test_prepare_invoice_data(self, mock_throw, mock_get_cached_doc, mock_get_doc):
        # Mocking the invoice document
        mock_invoice = MagicMock()
        mock_invoice.is_return = 0
        mock_invoice.posting_date = '2023-10-01'
        mock_invoice.posting_time = '12:00:00'
        mock_invoice.company = 'Test Company'
        mock_invoice.customer = 'Test Customer'
        mock_invoice.items = [MagicMock(item_code='ITEM001', qty=2, rate=100, amount=200)]
        mock_invoice.currency = 'USD'
        mock_invoice.conversion_rate = 1.0
        mock_invoice.remarks = 'Test Remarks'
        
        # Mocking the company document
        mock_company = MagicMock()
        mock_company.custom_default_item_class = 'DefaultClass'
        
        # Mocking the customer document
        mock_customer = MagicMock()
        mock_customer.tax_id = '1234567890'
        mock_customer.customer_name = 'Test Customer Name'
        
        # Mocking the branch
        mock_branch = {'custom_tpin': '1234567890', 'custom_bhf_id': '001'}
        
        # Setting up the return values for the mocked methods
        mock_get_doc.side_effect = lambda doctype, name: {
            'Sales Invoice': mock_invoice,
            'Company': mock_company,
            'Customer': mock_customer
        }[doctype]
        
        mock_get_cached_doc.side_effect = lambda doctype, name: {
            'Company': mock_company,
            'Customer': mock_customer
        }[doctype]
        
        # Call the function
        result = prepare_invoice_data(mock_invoice, branch=mock_branch)
        
        # Assertions
        self.assertIsInstance(result, str)  # Check if the result is a JSON string
        self.assertIn('"tpin": "1234567890"', result)  # Check if the TPIN is in the result
        self.assertIn('"custNm": "Test Customer Name"', result)  # Check if the customer name is in the result

if __name__ == '__main__':
    unittest.main()