app_name = "smart_invoice_app"
app_title = "Smart Invoice App"
app_publisher = "Bantoo and Partners"
app_description = "ERPNext Zambia Smart Invoice Integration"
app_email = "devs@thebantoo.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext", "frappe"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "smart_invoice_app",
# 		"logo": "/assets/smart_invoice_app/logo.png",
# 		"title": "Smart Invoice App",
# 		"route": "/smart_invoice_app",
# 		"has_permission": "smart_invoice_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/smart_invoice_app/css/smart_invoice_app.css"
# app_include_js = "/assets/smart_invoice_app/js/smart_invoice_app.js"

# app_include_js = '/assets/smart_invoice_app/js/customer_quick_entry.js'
app_include_js = 'smart_invoice_app.bundle.js'

# include js, css files in header of web template
# web_include_css = "/assets/smart_invoice_app/css/smart_invoice_app.css"
# web_include_js = "/assets/smart_invoice_app/js/smart_invoice_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "smart_invoice_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "smart_invoice_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "smart_invoice_app.utils.jinja_methods",
# 	"filters": "smart_invoice_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "smart_invoice_app.install.before_install"
# after_install = "smart_invoice_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "smart_invoice_app.uninstall.before_uninstall"
# after_uninstall = "smart_invoice_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "smart_invoice_app.utils.before_app_install"
# after_app_install = "smart_invoice_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "smart_invoice_app.utils.before_app_uninstall"
# after_app_uninstall = "smart_invoice_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "smart_invoice_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    "Item": {
        "after_insert": "smart_invoice_app.app.save_item_api",
        "on_update": "smart_invoice_app.app.update_item_api"
    },
    "BOM": {
        "on_submit": "smart_invoice_app.app.save_item_composition"
    },
    "Sales Invoice": {
        # "on_update": "smart_invoice_app.app.save_invoice_api",
        "on_submit": "smart_invoice_app.app.save_invoice_api",
        "on_cancel": "smart_invoice_app.app.delete_qr_code_file"
    },
    "Purchase Invoice": {
        # "on_update": "smart_invoice_app.app.save_purchase_invoice_api",
        "on_submit": "smart_invoice_app.app.save_purchase_invoice_api",
    },
    "Stock Ledger Entry": {
        "after_insert": "smart_invoice_app.app.update_stock_movement"
    },
    "POS Invoice": {
        "on_submit": "smart_invoice_app.app.save_invoice_api"
    },
    "Company": {
        "on_trash": "smart_invoice_app.app.delete_vat_settings_for_company"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"smart_invoice_app.tasks.all"
# 	],
# 	"daily": [
# 		"smart_invoice_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"smart_invoice_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"smart_invoice_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"smart_invoice_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "smart_invoice_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "smart_invoice_app.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "smart_invoice_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["smart_invoice_app.utils.before_request"]
# after_request = ["smart_invoice_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["smart_invoice_app.utils.before_job"]
# after_job = ["smart_invoice_app.utils.after_job"]

# User Data Protection
# --------------------
standard_doctypes = [
    "Sales Invoice",
    "Item",
    "Item Price",
    "Item Group",
    "Tax Category",
    "Sales Taxes and Charges",
    "Purchase Taxes and Charges",
    "Contact",
    "Customer",
    "Mode of Payment",
    "Supplier",
    "Country",
    "Mode of Payment Account",
    "Sales Invoice Item",
    "Purchase Invoice Item",
    "Stock Entry Item",
    "Stock Ledger Entry Item",
    "Item Price",
    "Item Group"    
]

# {
#     "doctype": "DocType Layout",
#     "filters": {
#         "name": ["in", standard_doctypes]
# }
# },
# {
#     "doctype": "Property Setter",
#     "filters": {
#         "name": ["in", standard_doctypes]
#     }
# },

fixtures = [
    {
        "doctype": "Client Script",
        "filters": [
            {
                "module": "Smart Invoice App"
            }
        ]
    },
    {
        "doctype": "Role",
        "filters": [
            {
                "role_name": "API User"
            }
        ]
    },
    {
        "doctype": "Province", 
    },
    {
        "doctype": "District", 
    },
    {
        "doctype": "Code Class", 
    },
    {
        "doctype": "Item Class", 
    },
    {
        "doctype": "Tax Category", 
    },
    {
        "doctype": "Code", 
    },
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "in", [
                "Manufacturer",
                "Item",
                "Item Price",
                "Item Group",
                "Tax Category",
                "Sales Taxes and Charges",
                "Purchase Taxes and Charges",
                "Contact"
                "Branch",
                "Customer",
                "Customer Branch",
                "Supplier",
                "Sales Invoice",
                "Purchase Invoice",
                "Stock Ledger Entry",
                "Mode of Payment",
                "Stock Entry",
                "UOM",
                "Company",
                "Country",
                "Mode of Payment",
                "Mode of Payment Account",
                "Sales Invoice Item",
                "Purchase Invoice Item",
                "Stock Entry Item",
                "Stock Ledger Entry Item",
                "Item Price",
                "Item Group",
                "Item Class",
                "Manufacturer"
            ]],
            ["modified", ">", "2024-09-26"]
        ]
    },
    {
        "doctype": "Property Setter",
        "filters": {
            "doc_type": ["in", [
                "Branch",
                "Customer",
                "Supplier",
                "Item Group",
                "Item",
                "Item Tax Template",
                "Tax Category",
                "Purchase Invoice",
                "Purchase Invoice Item",
                "Sales Invoice",
                "Sales Invoice Item",
                "BOM",
                "Company",
                "Delivery Note",
                "Purchase Receipt",
                "Stock Entry",
                "Contact",
                "Address",
            ]]
        }
    },
]

"""

"custom_column_break_o8y3c",
"custom_pkg_unit_cd",
"custom_pkg_unit",
"custom_column_break_jspfa",
"custom_item_cls_cd",
"custom_item_cls",
"custom_smart_invoice",
"custom_rental_yn",
"custom_svc_charge_yn",
"custom_manufacture_item_cd",
"default_manufacturer_part_no",
"custom_smart_invoice_manufacturer_details",
"custom_manufacturer_tpin",
"country_of_origin",
"""

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"smart_invoice_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

