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

  // ../smart_invoice_app/smart_invoice_app/public/js/smart_invoice_setup.js
  if (!$("link[href*='octicons']").length) {
    $("<link>").attr("rel", "stylesheet").attr("type", "text/css").attr("href", "https://cdnjs.cloudflare.com/ajax/libs/Octicons/4.4.0/font/octicons.min.css").appendTo("head");
  }
  var active_branch_dialog = null;
  var is_fetching_branch_context = false;
  var initiation_timeout = null;
  function enforce_branch_context() {
    if (initiation_timeout) {
      clearTimeout(initiation_timeout);
      initiation_timeout = null;
    }
    if (frappe.session.user && frappe.session.user !== "Guest" && !frappe.session.branch_doc_name) {
      render_navbar_branch_switcher(true);
      if (active_branch_dialog && active_branch_dialog.display || is_fetching_branch_context) {
        return;
      }
      initiation_timeout = setTimeout(function() {
        if (!frappe.session.branch_doc_name && !is_fetching_branch_context) {
          initialize_session_context(false);
        }
      }, 3e3);
    } else if (frappe.session.branch_doc_name) {
      render_navbar_branch_switcher(true, frappe.session.branch_doc_name);
    }
  }
  function render_navbar_branch_switcher(show_switcher, forced_label = null) {
    let $notifications_nav = $(".dropdown-notifications").closest("li");
    if (!$notifications_nav.length)
      return;
    let $switcher = $("#navbar-branch-switcher");
    let $separator = $("#navbar-branch-separator");
    if (!show_switcher) {
      $switcher.remove();
      $separator.remove();
      return;
    }
    let is_set = !!frappe.session.branch_doc_name;
    let label_text = forced_label || (is_set ? frappe.session.branch_doc_name || __("Branch Active") : __("Set Branch"));
    let icon_color = is_set ? "#17a2b8" : "pink";
    let switcher_html = `
        <li class="nav-item d-flex align-items-center" id="navbar-branch-switcher">
            <button class="btn-reset nav-link text-muted d-flex align-items-center" style="gap: 8px; padding: 0 10px; height: 100%; cursor: pointer;" title="${__("Switch active branch context")}">
                <span class="mega-octicon octicon-git-branch branch-icon-element" style="font-size: 16px; color: ${icon_color}; transition: color 0.2s ease;"></span>
                <span class="branch-label" style="color: var(--text-color); font-weight: 400; font-size: 13px;">${label_text}</span>
            </button>
        </li>
        <li class="vertical-bar d-none d-sm-block" id="navbar-branch-separator"></li>
    `;
    if ($switcher.length === 0) {
      $(switcher_html).insertBefore($notifications_nav);
      $("#navbar-branch-switcher button").on("click", function(e) {
        e.preventDefault();
        if (initiation_timeout) {
          clearTimeout(initiation_timeout);
        }
        initialize_session_context(true);
      });
    } else {
      $switcher.find(".branch-icon-element").css("color", icon_color);
      $switcher.find(".branch-label").text(label_text);
    }
  }
  $(document).ready(function() {
    enforce_branch_context();
    $(document).on("page-change", function() {
      enforce_branch_context();
    });
    $(document).on("click", 'button[onclick*="frappe.ui.toolbar.clear_cache()"]', function() {
      frappe.session.company = null;
      frappe.session.branch_doc_name = null;
      frappe.session.tpin = null;
      frappe.session.branch_code = null;
      frappe.call({
        method: "smart_invoice_app.scripts.setup.clear_session_branch_cache",
        async: false,
        callback: function(r) {
        }
      });
    });
  });
  function show_branch_success_alert(branch_doc_name, is_auto = false) {
    let alert_message = is_auto ? __(`Auto-assigned sole branch: <b>${branch_doc_name}</b>`) : __(`Branch set to: <b>${branch_doc_name}</b>`);
    frappe.show_alert({ message: alert_message, indicator: "green" });
  }
  function initialize_session_context(is_manual = false) {
    is_fetching_branch_context = true;
    frappe.call({
      method: "smart_invoice_app.scripts.setup.get_initial_session_status",
      callback: function(r) {
        if (r.error || !r.message) {
          console.error("Failed to parse initial session configuration.", r.error);
          is_fetching_branch_context = false;
          return;
        }
        let status = r.message;
        if (status.branch_code && !is_manual) {
          frappe.session.company = status.company;
          frappe.session.branch_doc_name = status.branch_doc_name;
          frappe.session.tpin = status.tpin;
          frappe.session.branch_code = status.branch_code;
          render_navbar_branch_switcher(true, status.branch_doc_name);
          is_fetching_branch_context = false;
          return;
        }
        if (!status.branches_setup) {
          is_fetching_branch_context = false;
          render_navbar_branch_switcher(false);
          if (frappe.get_route_str() === "List/Branch")
            return;
          if (frappe.session.user === "Administrator") {
            frappe.warn(
              __("Smart Invoice"),
              __("No branches with valid configurations were detected. Please navigate to the <b>Branch</b> list to set up Smart Invoice branches."),
              () => {
                frappe.set_route("List", "Branch");
              },
              __("Go to Branch Setup"),
              true
            );
            return;
          }
          if ($("#freeze-setup-notice").length === 0) {
            $(`<div id="freeze-setup-notice" style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); z-index: 9999; display: flex; justify-content: center; align-items: center; color: white; text-align: center; font-family: sans-serif;"><div><h2 style="color: #ff5858;">\u26A0\uFE0F Branch Assignment Required</h2><p style="margin: 15px 0; font-size: 16px;">Sorry, you are not assigned to any active Smart Invoice branches.<br>Please contact your Administrator or set up your Branch information.</p><button class="btn btn-primary" onclick="frappe.set_route('List', 'Branch'); $('#freeze-setup-notice').remove();" style="margin-top: 10px;">Go to Branch Setup</button></div></div>`).appendTo("body");
          }
          return;
        }
        if (status.auto_selected && status.branches && status.branches.length === 1) {
          frappe.session.company = status.company;
          frappe.session.branch_doc_name = status.branch_doc_name;
          frappe.session.tpin = status.tpin;
          frappe.session.branch_code = status.branch_code;
          render_navbar_branch_switcher(true, status.branch_doc_name);
          show_branch_success_alert(status.branch_doc_name, true);
          is_fetching_branch_context = false;
          return;
        }
        render_navbar_branch_switcher(true);
        show_branch_selection_dialog(status.branches);
      },
      always: function() {
        is_fetching_branch_context = false;
      }
    });
  }
  function show_branch_selection_dialog(branches) {
    if (active_branch_dialog && active_branch_dialog.display)
      return;
    let branch_options = branches.map((branch) => ({
      label: branch.branch_doc_name,
      value: branch.branch_doc_name
    }));
    active_branch_dialog = new frappe.ui.Dialog({
      title: __("Smart Invoice Branch"),
      fields: [
        {
          fieldtype: "Select",
          fieldname: "branch_doc_name",
          label: __("Branch"),
          options: branch_options,
          default: branches[0] ? branches[0].branch_doc_name : "",
          reqd: 1
        }
      ],
      primary_action_label: __("Save"),
      primary_action: function(values) {
        let selected_name = values ? values.branch_doc_name : this.get_value("branch_doc_name");
        let selected_branch = branches.find((b) => b.branch_doc_name === selected_name);
        if (selected_branch) {
          set_session_branch(selected_branch, this);
        }
      }
    });
    if (!frappe.session.branch_doc_name) {
      active_branch_dialog.$wrapper.find(".modal-header .close").hide();
      active_branch_dialog.get_close_btn().hide();
      active_branch_dialog.backdrop = "static";
      active_branch_dialog.keyboard = false;
      active_branch_dialog.$wrapper.on("hide.bs.modal", function(e) {
        if (!frappe.session.branch_doc_name) {
          e.preventDefault();
          e.stopPropagation();
          return false;
        }
      });
    }
    active_branch_dialog.show();
  }
  function set_session_branch(branch_data, dialog) {
    frappe.call({
      method: "smart_invoice_app.scripts.setup.set_branch",
      args: {
        branch_doc_name: branch_data.branch_doc_name,
        branch_code: branch_data.branch_code,
        tpin: branch_data.tpin,
        company: branch_data.company
      },
      callback: function(r) {
        if (!r.error && r.message) {
          frappe.session.company = r.message.company;
          frappe.session.branch_doc_name = r.message.branch_doc_name;
          frappe.session.tpin = r.message.tpin;
          frappe.session.branch_code = r.message.branch_doc_name;
          show_branch_success_alert(r.message.branch_doc_name);
          if (active_branch_dialog) {
            active_branch_dialog.$wrapper.off("hide.bs.modal");
          }
          dialog.hide();
          active_branch_dialog = null;
          render_navbar_branch_switcher(true, r.message.branch_doc_name);
        }
      }
    });
  }

  // ../smart_invoice_app/smart_invoice_app/public/js/realtime_listener.js
  $(document).ready(function() {
    initSmartInvoiceGlobalListener();
    console.log("apps/smart_invoice_app/smart_invoice_app/public/js/realtime_listener.js");
  });
  function initSmartInvoiceGlobalListener() {
    frappe.realtime.on("smart_invoice_event", function(data) {
      if (!data)
        return;
      if (data.type !== "print" && data.user && data.user !== frappe.session.user) {
        console.log("User mismatch ignored:", data.user);
        return;
      }
      const smart_invoice_docs = ["ASYCUDA Verification"];
      const activeFrm = window.cur_frm;
      const isViewingTargetDoc = !!(activeFrm && activeFrm.doc && (activeFrm.doc.name === data.name || data.type === "print" || data.function === "get_branches_testing"));
      const activeList = window.cur_list;
      const isViewingTargetList = !!(activeList && activeList.doctype && smart_invoice_docs.includes(activeList.doctype) && (activeList.doctype === data.doctype || data.type === "print"));
      if (isViewingTargetDoc) {
        console.log("Form:", data.name);
      } else {
        console.log("List:", activeList == null ? void 0 : activeList.doctype);
      }
      switch (data.type) {
        case "print":
          console.log(data.message || data.name);
          break;
        case "progress":
          if (!(isViewingTargetDoc || isViewingTargetList) && data.indicator !== "print") {
            console.log("Progress ignored (not in view):", data.name);
            return;
          }
          let indicator = data.indicator ? data.indicator.toLowerCase() : "blue";
          let message = data.message || __("Sync status update received.");
          if (indicator === "red") {
            frappe.warn(
              __("Smart Invoice encountered the following error:"),
              `${message}<br>`,
              () => {
                frappe.set_route("Form", "Sync Request", data.name);
              },
              __("Open")
            );
          } else if (indicator === "print") {
            console.log(message);
          } else if (indicator === "orange") {
            frappe.show_alert({ message, indicator }, 4);
          } else {
            frappe.show_alert({ message, indicator }, 3);
          }
          break;
        case "reload":
          let acted = false;
          if (isViewingTargetDoc && activeFrm) {
            console.log("Reloading form:", data.name);
            activeFrm.reload_doc();
            acted = true;
          }
          if (isViewingTargetList && activeList) {
            console.log("Refreshing list:", data.doctype);
            activeList.refresh();
            acted = true;
          }
          if (!acted) {
            console.log("Reload skipped (neither form nor list matched active view):", data.name);
          }
          break;
        default:
          console.warn("Unknown event type:", data.type);
      }
    });
  }
})();
//# sourceMappingURL=smart_invoice_app.bundle.A3KBIPCN.js.map
