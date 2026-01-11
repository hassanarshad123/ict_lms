# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""
Zoom webhook handler.

NOTE: Recording processing has been moved to the native Vimeo-Zoom integration.
This webhook handler is kept for:
1. URL validation (initial webhook setup)
2. Future event handling if needed

Recording workflow now uses:
- lms.lms.webhooks.vimeo_webhook.handle_vimeo_event
- lms.lms.doctype.lms_course_recording.vimeo_processor
"""

import json
import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def handle_zoom_event():
    """
    Handle incoming Zoom webhook events.

    Currently only handles URL validation for initial setup.
    Recording events are now handled by Vimeo webhooks.
    """
    try:
        if frappe.request.data:
            data = json.loads(frappe.request.data)
        else:
            return {"status": "error", "message": "No webhook data received"}

        # Handle Zoom URL validation challenge
        if data.get("event") == "endpoint.url_validation":
            return handle_url_validation(data)

        # Log other events for debugging but don't process
        event_type = data.get("event")
        frappe.logger().info(f"Zoom webhook event received (not processed): {event_type}")

        return {
            "status": "acknowledged",
            "event": event_type,
            "message": "Recording events are now handled by Vimeo integration"
        }

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON"}
    except Exception as e:
        frappe.log_error(f"Zoom webhook error: {str(e)}", "Zoom Webhook Error")
        return {"status": "error", "message": str(e)}


def handle_url_validation(data):
    """
    Handle Zoom's URL validation challenge.

    Zoom sends this when you first configure a webhook endpoint.
    Returns the plainToken as required by Zoom.
    """
    import hashlib
    import hmac

    plain_token = data.get("payload", {}).get("plainToken")

    if not plain_token:
        return {"status": "error", "message": "No plainToken in validation request"}

    # For URL validation, we need to return the encrypted token
    # Get webhook secret from Zoom Settings if configured
    zoom_settings = frappe.get_all(
        "LMS Zoom Settings",
        filters={"enabled": 1},
        fields=["name"],
        limit=1
    )

    secret = ""
    if zoom_settings:
        # Use a default secret or skip validation during setup
        secret = "zoom_webhook_secret"

    encrypted_token = hmac.new(
        secret.encode("utf-8"),
        plain_token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return {
        "plainToken": plain_token,
        "encryptedToken": encrypted_token,
    }
