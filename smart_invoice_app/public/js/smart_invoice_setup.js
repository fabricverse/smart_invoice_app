console.log('loaded: apps/smart_invoice_app/smart_invoice_app/public/js/smart_invoice_setup.js');

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
 * Core middleware synchronization logic. Hydrates local memory states from server-persisted user
 * defaults on application boot, and evaluates whether a branch context selection must be enforced.
 */
function enforce_branch_context() {
    // PERSISTENCE FALLBACK: Extract database values injected into frappe.boot on hard page reload
    if (frappe.boot && frappe.boot.user && frappe.boot.user.defaults) {
        let defaults = frappe.boot.user.defaults;
        if (defaults.custom_active_branch && !frappe.session.custom_active_branch) {
            frappe.session.custom_active_branch = defaults.custom_active_branch;
            frappe.session.custom_active_branch_name = defaults.custom_active_branch_name;
            frappe.session.tpin = defaults.custom_tpin;
            frappe.session.branch_code = defaults.custom_active_branch;
        }
    }

    // EVALUATION RULE: Enforce modal check workflow only if a valid user is logged in (ignores Guests)
    if (frappe.session.user && frappe.session.user !== 'Guest' && !frappe.session.custom_active_branch) {
        // Render unassigned state switcher widget (Pink alert condition indicator)
        render_navbar_branch_switcher(true);

        // Guard against double processing or overlapping prompts
        if ((active_branch_dialog && active_branch_dialog.display) || is_fetching_branch_context) {
            return; 
        }

        if (initiation_timeout) {
            clearTimeout(initiation_timeout);
        }

        // Debounce prompt configuration processing by 3 seconds to let desk workspace render smoothly
        initiation_timeout = setTimeout(function() {
            if (!frappe.session.custom_active_branch && !is_fetching_branch_context) {
                initialize_session_context();
            }
        }, 3000);
    } else if (frappe.session.custom_active_branch) {
        // Stable State: Context is set. Render active switcher widget (Cyan/Blue status state indicator)
        render_navbar_branch_switcher(true, frappe.session.custom_active_branch_name);
    }
}

/**
 * UI COMPONENT: Native UI Workspace Injector
 * Builds or refreshes the branch switching component inside Frappe's primary right-hand workspace utility tray.
 * Uses exact native layout node selectors to guarantee seamless element flow integration.
 * * @param {boolean} show_switcher - Toggle directive to mount or strip the element block from view.
 * @param {string|null} forced_label - Optional custom text override string (e.g. Assigned Active Branch Name).
 */
function render_navbar_branch_switcher(show_switcher, forced_label = null) {
    // Target notification bell item directly to avoid layout replication across multiple navbar lists
    let $notifications_nav = $('.dropdown-notifications').closest('li');
    if (!$notifications_nav.length) return;

    let $switcher = $('#navbar-branch-switcher');
    let $separator = $('#navbar-branch-separator');

    // Safe disposal path when branch context features are not allowed or unconfigured
    if (!show_switcher) {
        $switcher.remove();
        $separator.remove();
        return;
    }
    
    let is_set = !!frappe.session.custom_active_branch;
    let label_text = forced_label || (is_set ? (frappe.session.custom_active_branch_name || __('Branch Active')) : __('Set Branch'));
    
    // UI Theme Palette: Cyan/Blue implies operational readiness; Pink implies an action item is required
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

    // DOM Inject Manipulation Hook
    if ($switcher.length === 0) {
        $(switcher_html).insertBefore($notifications_nav);
        
        // Manual change trigger registration
        $('#navbar-branch-switcher button').on('click', function(e) {
            e.preventDefault();
            initialize_session_context();
        });
    } else {
        // Performance optimization: prevent complete redraws by targeting sub-properties directly
        $switcher.find('.branch-icon-element').css('color', icon_color);
        $switcher.find('.branch-label').text(label_text);
    }
}

/**
 * SYSTEM LIFE-CYCLE HOOKS
 * Hooks code execution hooks directly into general browser loading cycles and single-page routing trends.
 */
$(document).ready(function() {
    enforce_branch_context();
    
    // Re-verify session constraints on internal route navigation changes
    $(document).on('page-change', function() {
        enforce_branch_context();
    });
});

/**
 * CENTRALIZED GLOBAL ALERT
 * Provides a standardized visual green check prompt across all manual and auto-assignment routines.
 * * @param {string} branch_display_name - Display title name of the branch.
 */
function show_branch_success_alert(branch_display_name) {
    frappe.show_alert({
        message: __(`Branch set to: ${branch_display_name}`),
        indicator: 'green'
    });
}

/**
 * REMOTE DISPATCHER: Fetch Permission Records
 * Requests authorization payload details from the server backend to determine visibility logic.
 */
function initialize_session_context() {
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

            // NO BRANCHES SETUP CONDITION
            if (!status.branches_setup) {
                is_fetching_branch_context = false; 
                render_navbar_branch_switcher(false);

                if (frappe.get_route_str() === 'List/Branch') return;

                // RULE: If the logged-in user is the System Administrator, do NOT freeze their desk workspace.
                // Instead, issue a non-blocking notification so they can navigate to configuration screens.
                if (frappe.session.user === 'Administrator') {
                    frappe.warn(
                        __('Smart Invoice'),
                        __('No branches with valid configurations were detected. Please navigate to the <b>Branch</b> list to set up Smart Invoice branches.'),
                        () => {
                            // Action to take if they click the primary button (e.g., take them directly to setup)
                            frappe.set_route('List', 'Branch');
                        },
                        __('Go to Branch Setup'), // Primary button label
                        true // Makes it a non-dismissible/sticky modal if set to true, or omit for default close behavior
                    );
                    return;
                }

                // Lock workspace overlay to prompt administrative configurations
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

            // If backend auto-assigned a single available branch, consume variables immediately and skip dialog prompt
            if (status.auto_selected && status.branches && status.branches.length === 1) {
                frappe.session.custom_active_branch = status.active_branch_id;
                frappe.session.custom_active_branch_name = status.active_branch_name;
                frappe.session.tpin = status.active_tpin;
                frappe.session.branch_code = status.active_branch_id;
                
                render_navbar_branch_switcher(true, status.active_branch_name);
                show_branch_success_alert(status.active_branch_name);
                
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

/**
 * MODAL RENDERING: Multi-Branch Choice Selection Prompt
 * Generates and structures options within the choice prompt.
 * * @param {Array} branches - Map array of allowed branch dict items sent by the backend logic.
 */
function show_branch_selection_dialog(branches) {
    if (active_branch_dialog && active_branch_dialog.display) return;

    let branch_options = branches.map(branch => ({ 
        label: branch.name, 
        value: branch.name 
    }));

    active_branch_dialog = new frappe.ui.Dialog({
        title: __('Smart Invoice Branch'),
        fields: [
            {
                fieldtype: 'Select',
                fieldname: 'branch_doc_name',
                label: __('Branch'),
                options: branch_options,
                // Default value binds to index [0], which backend automatically populates with user-defined defaults
                default: branches[0] ? branches[0].name : "", 
                reqd: 1
            }
        ],
        primary_action_label: __('Save'),
        primary_action: function() {
            let selected_name = active_branch_dialog.get_value('branch_doc_name');
            let selected_branch = branches.find(b => b.name === selected_name);
            
            if (selected_branch) {
                set_session_branch(selected_branch, active_branch_dialog);
            }
        }
    });

    // BACKDROP ESCAPE LOCKOUT: If session state remains unassigned, freeze modal interaction escape paths
    if (!frappe.session.custom_active_branch) {
        active_branch_dialog.$wrapper.find('.modal-header .close').hide(); 
        active_branch_dialog.get_close_btn().hide();                       
        active_branch_dialog.backdrop = 'static';                          
        active_branch_dialog.keyboard = false;                             

        // Trap close actions sent via unexpected browser modal event bubbling routines
        active_branch_dialog.$wrapper.on('hide.bs.modal', function(e) {
            if (!frappe.session.custom_active_branch) {
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
 * Dispatches values to the server database database defaults backend cache engine.
 * * @param {Object} branch_data - Target data mapping parameters dictionary.
 * @param {Object} dialog - Current dialog modal reference payload.
 */
function set_session_branch(branch_data, dialog) {
    frappe.call({
        method: "smart_invoice_app.scripts.setup.set_branch",
        args: {
            branch_doc_name: branch_data.name,
            branch_id: branch_data.custom_bhf_id,
            tpin: branch_data.custom_tpin
        }, 
        callback: function(r) {
            if (!r.error && r.message) {
                // Update active local javascript memory runtime scopes
                frappe.session.custom_active_branch = r.message.branch_id; 
                frappe.session.custom_active_branch_name = r.message.branch_display_name; 
                frappe.session.tpin = r.message.tpin;
                frappe.session.branch_code = r.message.branch_id;

                // Display standardized message confirmation
                show_branch_success_alert(r.message.branch_display_name);

                // Unbind backdrop blocks and clear tracking flags smoothly
                active_branch_dialog.$wrapper.off('hide.bs.modal');
                dialog.hide();
                active_branch_dialog = null;
                
                // Repaint widget layout item states (Transitions configuration indicator from Pink to Cyan)
                render_navbar_branch_switcher(true, r.message.branch_display_name);
            }
        }
    });
}