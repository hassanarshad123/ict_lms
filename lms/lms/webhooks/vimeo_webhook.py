# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""
Vimeo webhook handler for processing video-created events.

This handles the native Vimeo-Zoom integration where:
1. Zoom automatically sends recordings to Vimeo
2. Vimeo sends webhook when video is created
3. LMS maps the recording to the correct live class
"""

import hashlib
import hmac
import json
import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def handle_vimeo_event():
    """
    Handle incoming Vimeo webhook events.

    Supported events:
    - video-created: Triggers recording mapping to live class

    Vimeo sends webhooks to:
    POST /api/method/lms.lms.webhooks.vimeo_webhook.handle_vimeo_event
    """
    try:
        # Get raw request data
        if frappe.request.data:
            data = json.loads(frappe.request.data)
        else:
            frappe.throw(_("No webhook data received"))

        # Log the incoming webhook for debugging
        frappe.logger().info(f"Vimeo webhook received: {data.get('webhook_type')}")

        # Validate webhook signature
        if not validate_webhook_signature():
            frappe.log_error(
                "Invalid Vimeo webhook signature",
                "Vimeo Webhook Security Error",
            )
            frappe.throw(_("Invalid webhook signature"), frappe.AuthenticationError)

        # Process the event
        webhook_type = data.get("webhook_type")
        payload = data.get("data", {})
        timestamp = data.get("timestamp")

        if webhook_type == "video-created":
            return handle_video_created(payload, timestamp)
        else:
            # Log unknown events for debugging
            frappe.log_error(
                f"Unknown Vimeo webhook event: {webhook_type}",
                "Vimeo Webhook Event",
            )
            return {"status": "ignored", "event": webhook_type}

    except json.JSONDecodeError:
        frappe.throw(_("Invalid JSON in webhook payload"))
    except Exception as e:
        frappe.log_error(
            f"Vimeo webhook error: {str(e)}",
            "Vimeo Webhook Error",
        )
        raise


def validate_webhook_signature():
    """
    Validate the Vimeo webhook signature.

    Vimeo sends: x-webhook-signature header with HMAC-SHA256 hash
    """
    # Get signature from headers
    signature = frappe.request.headers.get("x-webhook-signature")

    if not signature:
        # No signature header - check if secret is configured
        settings = frappe.get_single("LMS Vimeo Settings")
        secret = settings.get_password("vimeo_webhook_secret") if settings.vimeo_webhook_secret else ""

        if not secret:
            # No secret configured, skip validation (for initial setup/testing)
            frappe.log_error(
                "Vimeo webhook secret not configured - signature validation skipped",
                "Vimeo Webhook Warning",
            )
            return True
        else:
            # Secret configured but no signature in request
            return False

    # Get webhook secret
    settings = frappe.get_single("LMS Vimeo Settings")
    secret = settings.get_password("vimeo_webhook_secret") if settings.vimeo_webhook_secret else ""

    if not secret:
        # If no secret configured, skip validation
        frappe.log_error(
            "Vimeo webhook secret not configured - signature validation skipped",
            "Vimeo Webhook Warning",
        )
        return True

    # Calculate expected signature
    request_body = frappe.request.data.decode("utf-8")
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        request_body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    # Compare signatures
    return hmac.compare_digest(signature, expected_signature)


def handle_video_created(payload, timestamp):
    """
    Handle video-created event from Vimeo.

    This is triggered when Vimeo receives a recording from Zoom
    via the native Vimeo-Zoom integration.
    """
    from lms.lms.doctype.lms_vimeo_settings.lms_vimeo_settings import is_vimeo_enabled

    if not is_vimeo_enabled():
        return {"status": "skipped", "reason": "Vimeo integration disabled"}

    # Extract video URI (format: /videos/123456789)
    video_uri = payload.get("video_uri") or payload.get("clip_uri")

    if not video_uri:
        frappe.log_error(
            "video-created webhook missing video_uri",
            "Vimeo Webhook Error",
        )
        return {"status": "error", "reason": "Missing video_uri"}

    # Extract video ID from URI
    video_id = video_uri.split("/")[-1]

    if not video_id or not video_id.isdigit():
        frappe.log_error(
            f"Invalid video URI format: {video_uri}",
            "Vimeo Webhook Error",
        )
        return {"status": "error", "reason": "Invalid video_uri format"}

    # Check if recording already exists for this Vimeo video
    existing_recording = frappe.db.exists(
        "LMS Course Recording", {"vimeo_video_id": video_id}
    )

    if existing_recording:
        return {
            "status": "skipped",
            "reason": "Recording already exists",
            "recording": existing_recording,
        }

    # Enqueue background job to process the recording
    # This ensures quick webhook response while doing heavy work in background
    frappe.enqueue(
        "lms.lms.doctype.lms_course_recording.vimeo_processor.process_vimeo_recording",
        video_id=video_id,
        video_uri=video_uri,
        timestamp=timestamp,
        queue="default",
        timeout=600,  # 10 minutes timeout
    )

    return {
        "status": "accepted",
        "video_id": video_id,
        "message": "Recording processing enqueued",
    }
