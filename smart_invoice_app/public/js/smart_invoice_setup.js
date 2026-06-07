// console.log('loaded: apps/smart_invoice_app/smart_invoice_app/public/js/smart_invoice_setup.js');

/**
 * UTILITY: External Style Asset Injection
 * Dynamically injects GitHub Octicons CSS stylesheet to render the custom 'git-branch' vector markup.
 * Avoids direct reliance on Frappe's internal native SVG sprite cache maps.
 */
if (!$("link[href*='octicons']").length) {
    $('<link>')
        .attr('rel', 'stylesheet')
        .attr('type', 'text/css')
        .attr('href', 'https://cdnjs.cloudflare.com/ajax/libs/Octicons/4.4.0/font/octicons.min.css')
        .appendTo('head');
}

// Global scope states tracking runtime operational contexts
let active_branch_dialog = null;        // Stores instance reference of the active frappe.ui.Dialog modal
let is_fetching_branch_context = false;  // Mutex flag preventing concurrent parallel API check requests
let initiation_timeout = null;          // Debounce timer ID controlling initial modal rendering delay

/**
 * Core middleware synchronization logic. Evaluates whether a volatile Redis cache 
 * branch context selection must be enforced or recovered.
 */
function enforce_branch_context() {
    // FIX: Clear any pending timer immediately to prevent stale overlapping loops on quick page changes/refreshes
    if (initiation_timeout) {
        clearTimeout(initiation_timeout);
        initiation_timeout = null;
    }

    // EVALUATION RULE: Enforce modal check workflow only if a valid user is logged in (ignores Guests)
    if (frappe.session.user && frappe.session.user !== 'Guest' && !frappe.session.branch_doc_name) {
        // Render unassigned state switcher widget (Pink alert condition indicator)
        render_navbar_branch_switcher(true);

        // Guard against double processing or overlapping prompts
        if ((active_branch_dialog && active_branch_dialog.display) || is_fetching_branch_context) {
            return; 
        }

        // PRESERVED FEATURE (2): Debounce prompt configuration processing by 3 seconds to let desk workspace render smoothly
        initiation_timeout = setTimeout(function() {
            if (!frappe.session.branch_doc_name && !is_fetching_branch_context) {
                // Check the backend cache automatically on script initialization after delay (is_manual = false)
                initialize_session_context(false);
            }
        }, 3000);
        
    } else if (frappe.session.branch_doc_name) {
        // Stable State: Context is set. Render active switcher widget (Cyan/Blue status state indicator)
        render_navbar_branch_switcher(true, frappe.session.branch_doc_name);
    }
}

/**
 * UI COMPONENT: Native UI Workspace Injector
 */
function render_navbar_branch_switcher(show_switcher, forced_label = null) {
    let $notifications_nav = $('.dropdown-notifications').closest('li');
    if (!$notifications_nav.length) return;

    let $switcher = $('#navbar-branch-switcher');
    let $separator = $('#navbar-branch-separator');

    if (!show_switcher) {
        $switcher.remove();
        $separator.remove();
        return;
    }
    
    let is_set = !!frappe.session.branch_doc_name;
    let label_text = forced_label || (is_set ? (frappe.session.branch_doc_name || __('Branch Active')) : __('Set Branch'));
    let icon_color = is_set ? '#17a2b8' : 'pink'; 

    let switcher_html = `
        <li class="nav-item d-flex align-items-center" id="navbar-branch-switcher">
            <button class="btn-reset nav-link text-muted d-flex align-items-center" style="gap: 8px; padding: 0 10px; height: 100%; cursor: pointer;" title="${__('Switch active branch context')}">
                <span class="mega-octicon octicon-git-branch branch-icon-element" style="font-size: 16px; color: ${icon_color}; transition: color 0.2s ease;"></span>
                <span class="branch-label" style="color: var(--text-color); font-weight: 400; font-size: 13px;">${label_text}</span>
            </button>
        </li>
        <li class="vertical-bar d-none d-sm-block" id="navbar-branch-separator"></li>
    `;

    if ($switcher.length === 0) {
        $(switcher_html).insertBefore($notifications_nav);
        
        $('#navbar-branch-switcher button').on('click', function(e) {
            e.preventDefault();
            // If the user manually clicks the button, clear any running background timers and run instantly
            if (initiation_timeout) {
                clearTimeout(initiation_timeout);
            }
            // PRESERVED NEW FEATURE: Pass `true` to force open selection choices on manual navbar button interaction click
            initialize_session_context(true);
        });
    } else {
        $switcher.find('.branch-icon-element').css('color', icon_color);
        $switcher.find('.branch-label').text(label_text);
    }
}

/**
 * SYSTEM LIFE-CYCLE HOOKS
 */
$(document).ready(function() {
    enforce_branch_context();
    
    // Track internal route navigation changes
    $(document).on('page-change', function() {
        enforce_branch_context();
    });
    
    $(document).on('click', 'button[onclick*="frappe.ui.toolbar.clear_cache()"]', function() {
        // Drop client runtime variables instantly before the page forces a window reload
        frappe.session.company = null;
        frappe.session.branch_doc_name = null;
        frappe.session.tpin = null;
        frappe.session.branch_code = null;
        
        frappe.call({
            method: "smart_invoice_app.scripts.setup.clear_session_branch_cache",
            async: false, // Force synchronous execution so the backend clears BEFORE the page reloads
            callback: function(r) {
                // The backend cache key is now gone; Frappe's native reload flow takes over safely
            }
        });
    });
});

/**
 * CENTRALIZED GLOBAL ALERT
 */
function show_branch_success_alert(branch_doc_name, is_auto = false) {
    let alert_message = is_auto 
        ? __(`Auto-assigned sole branch: <b>${branch_doc_name}</b>`)
        : __(`Branch set to: <b>${branch_doc_name}</b>`);

    frappe.show_alert({ message: alert_message, indicator: 'green' });
}

/**
 * REMOTE DISPATCHER: Fetch Permission Records & Cache Properties
 * @param {boolean} is_manual - If true, bypasses automatic background restoration to show choice popups
 */
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

            // 1. RECOVERY PATH: Only intercept automatically on background load checks if NOT a manual click action
            if (status.branch_code && !is_manual) {
                frappe.session.company = status.company;
                frappe.session.branch_doc_name = status.branch_doc_name;
                frappe.session.tpin = status.tpin;
                frappe.session.branch_code = status.branch_code;
                
                render_navbar_branch_switcher(true, status.branch_doc_name);
                is_fetching_branch_context = false;
                return;
            }

            // 2. NO BRANCHES SETUP CONDITION
            if (!status.branches_setup) {
                is_fetching_branch_context = false; 
                render_navbar_branch_switcher(false);

                if (frappe.get_route_str() === 'List/Branch') return;

                if (frappe.session.user === 'Administrator') {
                    frappe.warn(
                        __('Smart Invoice'),
                        __('No branches with valid configurations were detected. Please navigate to the <b>Branch</b> list to set up Smart Invoice branches.'),
                        () => { frappe.set_route('List', 'Branch'); },
                        __('Go to Branch Setup'),
                        true
                    );
                    return;
                }

                if ($("#freeze-setup-notice").length === 0) {
                    $('<div id="freeze-setup-notice" style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); z-index: 9999; display: flex; justify-content: center; align-items: center; color: white; text-align: center; font-family: sans-serif;">' +
                        '<div>' +
                            '<h2 style="color: #ff5858;">⚠️ Branch Assignment Required</h2>' +
                            '<p style="margin: 15px 0; font-size: 16px;">Sorry, you are not assigned to any active Smart Invoice branches.<br>Please contact your Administrator or set up your Branch information.</p>' +
                            '<button class="btn btn-primary" onclick="frappe.set_route(\'List\', \'Branch\'); $(\'#freeze-setup-notice\').remove();" style="margin-top: 10px;">Go to Branch Setup</button>' +
                        '</div>' +
                      '</div>').appendTo('body');
                }
                return;
            }

            // 3. AUTO-ASSIGN PATH: If system assigned a single choice option layout context automatically
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

            // 4. MULTI-CHOICE PATH: Present Selection Dialog
            render_navbar_branch_switcher(true);
            show_branch_selection_dialog(status.branches);
        },
        always: function() {
            is_fetching_branch_context = false;
        }
    });
}

/**
 * MODAL RENDERING: Multi-Branch Choice Selection Prompt
 */
function show_branch_selection_dialog(branches) {
    if (active_branch_dialog && active_branch_dialog.display) return;

    let branch_options = branches.map(branch => ({ 
        label: branch.branch_doc_name, 
        value: branch.branch_doc_name 
    }));

    active_branch_dialog = new frappe.ui.Dialog({
        title: __('Smart Invoice Branch'),
        fields: [
            {
                fieldtype: 'Select',
                fieldname: 'branch_doc_name',
                label: __('Branch'),
                options: branch_options,
                default: branches[0] ? branches[0].branch_doc_name : "", 
                reqd: 1
            }
        ],
        primary_action_label: __('Save'),
        primary_action: function(values) {
            let selected_name = values ? values.branch_doc_name : this.get_value('branch_doc_name');
            let selected_branch = branches.find(b => b.branch_doc_name === selected_name);
            
            if (selected_branch) {
                set_session_branch(selected_branch, this);
            }
        }
    });

    if (!frappe.session.branch_doc_name) {
        active_branch_dialog.$wrapper.find('.modal-header .close').hide(); 
        active_branch_dialog.get_close_btn().hide();                       
        active_branch_dialog.backdrop = 'static';                          
        active_branch_dialog.keyboard = false;                             

        active_branch_dialog.$wrapper.on('hide.bs.modal', function(e) {
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
                    active_branch_dialog.$wrapper.off('hide.bs.modal');
                }
                dialog.hide();
                active_branch_dialog = null;
                
                render_navbar_branch_switcher(true, r.message.branch_doc_name);
            }
        }
    });
}