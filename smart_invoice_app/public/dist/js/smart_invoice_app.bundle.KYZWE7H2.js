(() => {
  // ../smart_invoice_app/smart_invoice_app/public/js/customer_quick_entry.js
  frappe.provide("frappe.ui.form");
  frappe.ui.form.CustomerQuickEntryForm = class ContactAddressQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(doctype, after_insert, init_callback, doc, force) {
      super(doctype, after_insert, init_callback, doc, force);
      this.skip_redirect_on_error = true;
    }
    render_dialog() {
      this.mandatory = this.mandatory.concat(this.get_variant_fields());
      super.render_dialog();
    }
    validate() {
      const tpin = this.dialog.doc.tax_id;
      if (tpin && tpin.length !== 10) {
        frappe.show_alert({
          message: __("TPIN must be 10 digits"),
          indicator: "red"
        }, 5);
        return false;
      }
      const mobile_number = this.dialog.doc.mobile_number;
      if (mobile_number && mobile_number.length !== 10) {
        frappe.show_alert({
          message: __("Phone Number must be 10 digits"),
          indicator: "red"
        }, 5);
        return false;
      }
      return true;
    }
    insert() {
      if (!this.validate()) {
        this.dialog.hide();
        super.render_dialog();
        return false;
      }
      const map_field_names = {
        email_address: "email_id",
        mobile_number: "mobile_no"
      };
      Object.entries(map_field_names).forEach(([fieldname, new_fieldname]) => {
        this.dialog.doc[new_fieldname] = this.dialog.doc[fieldname];
        delete this.dialog.doc[fieldname];
      });
      return super.insert();
    }
    get_variant_fields() {
      var variant_fields = [
        {
          fieldtype: "Section Break",
          label: __("Contact Details"),
          collapsible: 0
        },
        {
          label: __("Address Line 1"),
          fieldname: "address_line1",
          fieldtype: "Data",
          reqd: 1
        },
        {
          label: __("Address Line 2 (Optional)"),
          fieldname: "address_line2",
          fieldtype: "Data"
        },
        {
          fieldtype: "Column Break"
        },
        {
          label: __("City"),
          fieldname: "city",
          fieldtype: "Data",
          reqd: 1
        },
        {
          label: __("Country"),
          fieldname: "country",
          fieldtype: "Link",
          options: "Country",
          default: "Zambia",
          reqd: 1
        },
        {
          label: __("Customer POS Id"),
          fieldname: "customer_pos_id",
          fieldtype: "Data",
          hidden: 1
        },
        {
          fieldtype: "Section Break"
        },
        {
          label: __("Phone Number"),
          fieldname: "mobile_number",
          fieldtype: "Data",
          reqd: 1
        },
        {
          fieldtype: "Column Break"
        },
        {
          label: __("Email (Optional)"),
          fieldname: "email_address",
          fieldtype: "Data",
          options: "Email"
        }
      ];
      return variant_fields;
    }
  };
})();
//# sourceMappingURL=smart_invoice_app.bundle.KYZWE7H2.js.map
