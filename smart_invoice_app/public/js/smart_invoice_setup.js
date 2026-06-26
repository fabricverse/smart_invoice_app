// Purpose: Adds smart invoice branch switcher button and functionality to the right of awesome search bar
//
// add icon to switcher button
if (!$("link[href*='octicons']").length) {
    $("<link>")
        .attr("rel", "stylesheet")
        .attr("type", "text/css")
        .attr(
            "href",
            "https://cdnjs.cloudflare.com/ajax/libs/Octicons/4.4.0/font/octicons.min.css",
        )
        .appendTo("head");
}

// Global scope states tracking runtime operational contexts
let active_branch_dialog = null; // Stores instance reference of the active frappe.ui.Dialog modal
let is_fetching_branch_context = false; // Mutex flag preventing concurrent parallel API check requests
let initiation_timeout = null; // Debounce timer ID controlling initial modal rendering delay

/**
 * HELPER: Synchronizes selected company across client-side defaults for form rendering
 */
function update_company_defaults(company) {
    if (!frappe.user_defaults) frappe.user_defaults = {};
    if (company) {
        frappe.user_defaults.company = company;
    } else {
        delete frappe.user_defaults.company;
    }

    // Also update standard boot defaults to ensure core Frappe link fields auto-populate correctly
    if (frappe.boot && frappe.boot.user && frappe.boot.user.defaults) {
        if (company) {
            frappe.boot.user.defaults.company = company;
        } else {
            delete frappe.boot.user.defaults.company;
        }
    }
}

/**
 * Core middleware synchronization logic.
 */
function enforce_branch_context() {
    if (initiation_timeout) {
        clearTimeout(initiation_timeout);
        initiation_timeout = null;
    }

    if (
        frappe.session.user &&
        frappe.session.user !== "Guest" &&
        !frappe.session.branch_doc_name
    ) {
        render_navbar_branch_switcher(true);

        if (
            (active_branch_dialog && active_branch_dialog.display) ||
            is_fetching_branch_context
        ) {
            return;
        }

        initiation_timeout = setTimeout(function () {
            if (
                !frappe.session.branch_doc_name &&
                !is_fetching_branch_context
            ) {
                initialize_session_context(false);
            }
        }, 2300);
    } else if (frappe.session.branch_doc_name) {
        render_navbar_branch_switcher(true);
    }
}

/**
 * UI COMPONENT: Native UI Workspace Injector
 */
function render_navbar_branch_switcher(show_switcher) {
    let $notifications_nav = $(".dropdown-notifications").closest("li");
    if (!$notifications_nav.length) return;

    let $switcher = $("#navbar-branch-switcher");
    let $separator = $("#navbar-branch-separator");

    if (!show_switcher) {
        $switcher.remove();
        $separator.remove();
        return;
    }

    let is_set = !!frappe.session.branch_doc_name;
    let label_text = __("Set Branch");

    if (is_set) {
        let company = frappe.session.company || "";
        let company_initials = company
            .split(/\s+/)
            .filter(Boolean)
            .map((w) => w[0])
            .join("")
            .toUpperCase();
        let branch = frappe.session.branch_doc_name || "";
        let clean_branch = branch.replace(/ - \d+$/, "");
        label_text = company_initials
            ? `${company_initials} - ${clean_branch}`
            : clean_branch;
    }

    let icon_color = is_set ? "#17a2b8" : "pink";

    let switcher_html = `
        <li class="nav-item d-flex align-items-center" id="navbar-branch-switcher">
            <button class="btn-reset nav-link text-muted d-flex align-items-center" style="gap: 8px; padding: 0 10px; height: 100%; cursor: pointer;" title="${__("Select the branch to work on")}">
                <span class="mega-octicon octicon-git-branch branch-icon-element" style="font-size: 16px; color: ${icon_color}; transition: color 0.2s ease;"></span>
                <span class="branch-label" style="color: var(--text-color); font-weight: 400; font-size: 13px;">${label_text}</span>
            </button>
        </li>
        <li class="vertical-bar d-none d-sm-block" id="navbar-branch-separator"></li>
    `;

    if ($switcher.length === 0) {
        $(switcher_html).insertBefore($notifications_nav);

        $("#navbar-branch-switcher button").on("click", function (e) {
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

/**
 * SYSTEM LIFE-CYCLE HOOKS
 */
$(document).ready(function () {
    // Prevent layout shift/jitter globally when modals open
    document.documentElement.style.scrollbarGutter = "stable";

    enforce_branch_context();

    // --- Global Form Save Interceptor for Company Default Mismatches ---
    if (frappe.ui && frappe.ui.form && frappe.ui.form.Form) {
        const original_form_save = frappe.ui.form.Form.prototype.save;

        frappe.ui.form.Form.prototype.save = function (
            action,
            callback,
            btn,
            on_error,
        ) {
            let frm = this;
            let default_company = frappe.user_defaults
                ? frappe.user_defaults.company
                : null;

            let active_branch = __("Active Branch");
            if (frappe.session.branch_doc_name) {
                let company = frappe.session.company || "";
                let company_initials = company
                    .split(/\s+/)
                    .filter(Boolean)
                    .map((w) => w[0])
                    .join("")
                    .toUpperCase();
                let clean_branch = frappe.session.branch_doc_name.replace(
                    / - \d+$/,
                    "",
                );
                active_branch = company_initials
                    ? `${company_initials} - ${clean_branch}`
                    : clean_branch;
            }

            const exclusions = [
                "Smart Invoice Settings",
                "Branch",
                "Company",
                "System Defaults",
            ];
            // Trigger prompt only if the form handles a company and it differs from the workspace branch default
            if (
                !exclusions.includes(frm.doctype) &&
                frm.doc &&
                frm.doc.company &&
                default_company &&
                frm.doc.company !== default_company
            ) {
                // Break recursive loop if user has already accepted the pop-up prompt
                if (frm.__company_warning_confirmed) {
                    delete frm.__company_warning_confirmed;
                    return original_form_save.call(
                        this,
                        action,
                        callback,
                        btn,
                        on_error,
                    );
                }

                $("body").css("overflow-y", "scroll");

                // Execute the native warning dialog with the correct argument layout
                frappe.warn(
                    __("Did you select the right company?"), // 1. Title
                    __(
                        "You are currently on branch <b>{1}</b> which isn't from the company (<b>{0}</b>) you've used on this document. Continue anyway?",
                        [frm.doc.company, active_branch],
                    ), // 2. Message Body
                    () => {
                        // 3. Proceed Action (Runs when primary button is clicked)
                        frm.__company_warning_confirmed = true;
                        original_form_save.call(
                            frm,
                            action,
                            callback,
                            btn,
                            on_error,
                        );
                    },
                    __("Continue"), // 4. Primary Button Text Label
                    false, // 5. Minimizable window toggle
                );
                return; // Halt current execution thread to await modal click
            }

            return original_form_save.call(
                this,
                action,
                callback,
                btn,
                on_error,
            );
        };
    }

    $(document).on("page-change", function () {
        enforce_branch_context();
    });

    $(document).on(
        "click",
        'button[onclick*="frappe.ui.toolbar.clear_cache()"]',
        function () {
            frappe.session.company = null;
            frappe.session.branch_doc_name = null;
            frappe.session.tpin = null;
            frappe.session.branch_code = null;
            update_company_defaults(null); // Clear defaults on logout/cache reset

            frappe.call({
                method: "smart_invoice_app.scripts.setup.clear_session_branch_cache",
                async: false,
                callback: function (r) {},
            });
        },
    );

    // Native Page Visibility API Event Listener
    // Catches silent background flushes the exact moment the user brings focus back to this tab
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible")
            verify_server_session_integrity();
    });
    window.addEventListener("focus", verify_server_session_integrity);
});

/**
 * UNIFIED WATCHDOG: Checks server state but honors the active mutex flag
 */
function verify_server_session_integrity() {
    // Guard flag: If we are already running an API call, abort to prevent double pings
    if (is_fetching_branch_context) return;

    if (frappe.session.user && frappe.session.user !== "Guest") {
        if (!frappe.session.branch_doc_name) {
            enforce_branch_context();
            return;
        }

        is_fetching_branch_context = true; // Raise the flag immediately

        frappe.call({
            method: "smart_invoice_app.scripts.setup.get_initial_session_status",
            callback: function (r) {
                if (r.message && !r.message.branch_code) {
                    frappe.session.company = null;
                    frappe.session.branch_doc_name = null;
                    frappe.session.tpin = null;
                    frappe.session.branch_code = null;
                    update_company_defaults(null); // Clear defaults if integrity check fails

                    enforce_branch_context();
                }
            },
            always: function () {
                is_fetching_branch_context = false; // Lower the flag when the network request completes
            },
        });
    }
}

function show_branch_success_alert(branch_doc_name, is_auto = false) {
    let company = frappe.session.company || "";
    let company_initials = company
        .split(/\s+/)
        .filter(Boolean)
        .map((w) => w[0])
        .join("")
        .toUpperCase();
    let clean_branch = branch_doc_name.replace(/ - \d+$/, "");
    let formatted_label = company_initials
        ? `${company_initials} - ${clean_branch}`
        : clean_branch;

    let alert_message = is_auto
        ? __(`Auto-assigned sole branch: <b>${formatted_label}</b>`)
        : __(`Branch set to: <b>${formatted_label}</b>`);

    frappe.show_alert({ message: alert_message, indicator: "green" });
}

/**
 * REMOTE DISPATCHER: Fetch Permission Records
 */
function initialize_session_context(is_manual = false) {
    is_fetching_branch_context = true;

    frappe.call({
        method: "smart_invoice_app.scripts.setup.get_initial_session_status",
        callback: function (r) {
            if (r.error || !r.message) {
                console.error(
                    "Failed to parse initial session configuration.",
                    r.error,
                );
                is_fetching_branch_context = false;
                return;
            }

            let status = r.message;

            if (status.branch_code && !is_manual) {
                frappe.session.company = status.company;
                frappe.session.branch_doc_name = status.branch_doc_name;
                frappe.session.tpin = status.tpin;
                frappe.session.branch_code = status.branch_code;
                update_company_defaults(status.company); // Set active default company

                render_navbar_branch_switcher(true);
                is_fetching_branch_context = false;
                return;
            }

            if (
                !status.branches_setup ||
                !status.branches ||
                status.branches.length === 0
            ) {
                is_fetching_branch_context = false;
                render_navbar_branch_switcher(false);

                if (frappe.get_route_str() === "List/Branch") return;

                if (frappe.session.user === "Administrator") {
                    frappe.warn(
                        __("Smart Invoice"),
                        __(
                            "No branches with valid configurations were detected. Please navigate to the <b>Branch</b> list to set up Smart Invoice branches.",
                        ),
                        () => {
                            frappe.set_route("List", "Branch");
                        },
                        __("Go to Branch Setup"),
                        true,
                    );
                    return;
                }

                if ($("#freeze-setup-notice").length === 0) {
                    $(
                        '<div id="freeze-setup-notice" style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); z-index: 9999; display: flex; justify-content: center; align-items: center; color: white; text-align: center; font-family: sans-serif;">' +
                            "<div>" +
                            '<h2 style="color: #ff5858;">⚠️ Branch Assignment Required</h2>' +
                            '<p style="margin: 15px 0; font-size: 16px;">Sorry, you are not assigned to any active Smart Invoice branches.<br>Please contact your Administrator or set up your Branch information.</p>' +
                            "<button class=\"btn btn-primary\" onclick=\"frappe.set_route('List','Branch'); $('#freeze-setup-notice').remove();\" style=\"margin-top: 10px;\">Go to Branch Setup</button>" +
                            "</div>" +
                            "</div>",
                    ).appendTo("body");
                }
                return;
            }

            if (
                status.auto_selected &&
                status.branches &&
                status.branches.length === 1
            ) {
                frappe.session.company = status.company;
                frappe.session.branch_doc_name = status.branch_doc_name;
                frappe.session.tpin = status.tpin;
                frappe.session.branch_code = status.branch_code;
                update_company_defaults(status.company); // Set active default company

                render_navbar_branch_switcher(true);
                show_branch_success_alert(status.branch_doc_name, true);

                is_fetching_branch_context = false;
                return;
            }

            render_navbar_branch_switcher(true);
            show_branch_selection_dialog(status.branches);
        },
        always: function () {
            is_fetching_branch_context = false;
        },
    });
}

/**
 * MODAL RENDERING: Multi-Branch Choice Selection Prompt
 */
function show_branch_selection_dialog(branches) {
    if (active_branch_dialog && active_branch_dialog.display) return;

    let branch_options = branches
        .filter((b) => b && b.branch_doc_name)
        .map((branch) => {
            let company = branch.company || "";
            let company_initials = company
                .split(/\s+/)
                .filter(Boolean)
                .map((w) => w[0])
                .join("")
                .toUpperCase();
            let clean_branch = branch.branch_doc_name.replace(/ - \d+$/, "");
            return {
                label: company_initials
                    ? `${company_initials} - ${clean_branch}`
                    : clean_branch,
                value: branch.branch_doc_name,
            };
        });

    if (branch_options.length === 0) return;

    active_branch_dialog = new frappe.ui.Dialog({
        title: __("Smart Invoice Branch"),
        fields: [
            {
                fieldtype: "Select",
                fieldname: "branch_doc_name",
                label: __("Branch"),
                options: branch_options,
                default: branch_options[0] ? branch_options[0].value : "",
                reqd: 1,
            },
        ],
        primary_action_label: __("Save"),
        primary_action: function (values) {
            let selected_name = values
                ? values.branch_doc_name
                : this.get_value("branch_doc_name");
            let selected_branch = branches.find(
                (b) => b.branch_doc_name === selected_name,
            );

            if (selected_branch) {
                set_session_branch(selected_branch, this);
            }
        },
    });

    if (!frappe.session.branch_doc_name) {
        active_branch_dialog.$wrapper.find(".modal-header .close").hide();
        active_branch_dialog.get_close_btn().hide();
        active_branch_dialog.backdrop = "static";
        active_branch_dialog.keyboard = false;

        active_branch_dialog.$wrapper.on("hide.bs.modal", function (e) {
            if (!frappe.session.branch_doc_name) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
        });
    }

    active_branch_dialog.show();
}

/**
 * REMOTE CALL: Commit Session Updates
 */
function set_session_branch(branch_data, dialog) {
    frappe.call({
        method: "smart_invoice_app.scripts.setup.set_branch",
        args: {
            branch_doc_name: branch_data.branch_doc_name,
            branch_code: branch_data.branch_code,
            tpin: branch_data.tpin,
            company: branch_data.company,
        },
        callback: function (r) {
            if (!r.error && r.message) {
                frappe.session.company = r.message.company;
                frappe.session.branch_doc_name = r.message.branch_doc_name;
                frappe.session.tpin = r.message.tpin;
                frappe.session.branch_code = r.message.branch_code;
                update_company_defaults(r.message.company); // Set active default company

                show_branch_success_alert(r.message.branch_doc_name);

                if (active_branch_dialog) {
                    active_branch_dialog.$wrapper.off("hide.bs.modal");
                }
                dialog.hide();
                active_branch_dialog = null;

                render_navbar_branch_switcher(true);
            }
        },
    });
}
