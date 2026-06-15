$(document).ready(function () {
    initSmartInvoiceGlobalListener();
    setupVisibilityFocusRecovery(); // Added visibility change watcher
    // console.log(
    //     "apps/smart_invoice_app/smart_invoice_app/public/js/realtime_listener.js",
    // );
});

function initSmartInvoiceGlobalListener() {
    // Turn off any existing listener for this event first to prevent duplicate bindings on re-init
    frappe.realtime.off("smart_invoice_event");

    frappe.realtime.on("smart_invoice_event", function (data) {
        if (!data) return;

        // User Verification Guard (Ignored strictly for "print" types)
        if (
            data.type !== "print" &&
            data.user &&
            data.user !== frappe.session.user
        ) {
            console.log("User mismatch ignored:", data.user);
            return;
        }

        // Define which DocTypes belong to the Smart Invoice ecosystem
        const smart_invoice_docs = [
            "ASYCUDA Verification",
            "Purchase Invoice",
            "Branch",
            "Item",
        ];

        // Form Context
        const activeFrm = window.cur_frm;
        const isViewingTargetDoc = !!(
            activeFrm &&
            activeFrm.doc &&
            (activeFrm.doc.name === data.name ||
                data.type === "print" ||
                data.function === "get_branches_testing")
        );

        // List View Context - Dynamically matches ecosystem list view AND the incoming doctype target
        const activeList = window.cur_list;
        const isViewingTargetList = !!(
            activeList &&
            activeList.doctype &&
            smart_invoice_docs.includes(activeList.doctype) &&
            (activeList.doctype === data.doctype || data.type === "print")
        );

        if (isViewingTargetDoc) {
            console.log("Form:", data.name);
        } else {
            console.log("List:", activeList?.doctype);
        }

        switch (data.type) {
            case "print":
                console.log(data.message || data.name);
                break;

            case "progress":
                if (
                    !(isViewingTargetDoc || isViewingTargetList) &&
                    data.indicator !== "print"
                ) {
                    console.log("Progress ignored (not in view):", data.name);
                    return;
                }

                let indicator = data.indicator
                    ? data.indicator.toLowerCase()
                    : "blue";
                let message =
                    data.message || __("Sync status update received.");

                if (indicator === "red") {
                    frappe.warn(
                        __("Smart Invoice encountered the following error:"),
                        `${message}<br>`,
                        () => {
                            frappe.set_route("Form", "Sync Request", data.name);
                        },
                        __("Open"),
                    );
                } else if (indicator === "print") {
                    console.log(message);
                } else if (indicator === "orange") {
                    frappe.show_alert(
                        { message: message, indicator: indicator },
                        4,
                    );
                } else {
                    frappe.show_alert(
                        { message: message, indicator: indicator },
                        3,
                    );
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
                    console.log(
                        "Reload skipped (neither form nor list matched active view):",
                        data.name,
                    );
                }
                break;

            default:
                console.warn("Unknown event type:", data.type);
        }
    });
}

/**
 * Monitors page visibility. If the tab becomes active after being in the background,
 * it ensures the Frappe socket connection is alive and refreshes the listener.
 */
function setupVisibilityFocusRecovery() {
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible") {
            // Check if socket exists and is disconnected
            if (frappe.realtime.socket && !frappe.realtime.socket.connected) {
                console.log("Socket disconnected. Forcing reconnect...");
                frappe.realtime.socket.connect();
            }

            // Re-initialize listener to guarantee it is active and fresh
            initSmartInvoiceGlobalListener();
        }
    });
}
