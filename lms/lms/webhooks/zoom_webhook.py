# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""
Zoom webhook handler for processing recording.completed events.
"""

import hashlib
import hmac
import json
import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def handle_zoom_event():
	"""
	Handle incoming Zoom webhook events.

	Supported events:
	- recording.completed: Triggers recording upload to Vimeo

	Zoom sends webhooks to:
	POST /api/method/lms.lms.webhooks.zoom_webhook.handle_zoom_event
	"""
	try:
		# Get raw request data
		if frappe.request.data:
			data = json.loads(frappe.request.data)
		else:
			frappe.throw(_("No webhook data received"))

		# Handle Zoom URL validation challenge
		if data.get("event") == "endpoint.url_validation":
			return handle_url_validation(data)

		# Validate webhook signature
		if not validate_webhook_signature():
			frappe.throw(_("Invalid webhook signature"), frappe.AuthenticationError)

		# Process the event
		event_type = data.get("event")
		payload = data.get("payload", {})

		if event_type == "recording.completed":
			return handle_recording_completed(payload)
		else:
			# Log unknown events for debugging
			frappe.log_error(
				f"Unknown Zoom webhook event: {event_type}",
				"Zoom Webhook Event",
			)
			return {"status": "ignored", "event": event_type}

	except json.JSONDecodeError:
		frappe.throw(_("Invalid JSON in webhook payload"))
	except Exception as e:
		frappe.log_error(
			f"Zoom webhook error: {str(e)}",
			"Zoom Webhook Error",
		)
		raise


def handle_url_validation(data):
	"""
	Handle Zoom's URL validation challenge.
	Zoom sends this when you first configure a webhook endpoint.
	"""
	plain_token = data.get("payload", {}).get("plainToken")

	if not plain_token:
		frappe.throw(_("No plainToken in validation request"))

	# Get webhook secret
	settings = frappe.get_single("LMS Vimeo Settings")
	secret = settings.get_password("webhook_secret") if settings.webhook_secret else ""

	# Create encrypted token
	encrypted_token = hmac.new(
		secret.encode("utf-8"), plain_token.encode("utf-8"), hashlib.sha256
	).hexdigest()

	return {
		"plainToken": plain_token,
		"encryptedToken": encrypted_token,
	}


def validate_webhook_signature():
	"""
	Validate the Zoom webhook signature.
	"""
	# Get signature from headers
	signature = frappe.request.headers.get("x-zm-signature")
	timestamp = frappe.request.headers.get("x-zm-request-timestamp")

	if not signature or not timestamp:
		return False

	# Get webhook secret
	settings = frappe.get_single("LMS Vimeo Settings")
	secret = settings.get_password("webhook_secret") if settings.webhook_secret else ""

	if not secret:
		# If no secret configured, skip validation (not recommended for production)
		frappe.log_error(
			"Zoom webhook secret not configured - signature validation skipped",
			"Zoom Webhook Warning",
		)
		return True

	# Construct the message
	message = f"v0:{timestamp}:{frappe.request.data.decode('utf-8')}"

	# Calculate expected signature
	expected_signature = "v0=" + hmac.new(
		secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
	).hexdigest()

	# Compare signatures
	return hmac.compare_digest(signature, expected_signature)


def handle_recording_completed(payload):
	"""
	Handle recording.completed event from Zoom.

	Creates LMS Course Recording and enqueues upload job.
	"""
	from lms.lms.doctype.lms_vimeo_settings.lms_vimeo_settings import is_vimeo_enabled

	if not is_vimeo_enabled():
		return {"status": "skipped", "reason": "Vimeo integration disabled"}

	meeting_object = payload.get("object", {})
	meeting_uuid = meeting_object.get("uuid")
	meeting_id = meeting_object.get("id")
	topic = meeting_object.get("topic", "Untitled Recording")
	duration = meeting_object.get("duration", 0)  # In minutes
	start_time = meeting_object.get("start_time")
	recording_files = meeting_object.get("recording_files", [])

	if not meeting_uuid:
		frappe.log_error(
			"Recording completed webhook missing meeting UUID",
			"Zoom Webhook Error",
		)
		return {"status": "error", "reason": "Missing meeting UUID"}

	# Find the live class by UUID
	live_class_name = frappe.db.get_value(
		"LMS Live Class", {"uuid": meeting_uuid}, "name"
	)

	if not live_class_name:
		# Try matching by meeting_id
		live_class_name = frappe.db.get_value(
			"LMS Live Class", {"meeting_id": str(meeting_id)}, "name"
		)

	if not live_class_name:
		frappe.log_error(
			f"No LMS Live Class found for meeting UUID: {meeting_uuid}, ID: {meeting_id}",
			"Zoom Webhook Warning",
		)
		return {"status": "skipped", "reason": "No matching live class found"}

	# Check if recording already exists
	existing_recording = frappe.db.exists(
		"LMS Course Recording", {"live_class": live_class_name}
	)

	if existing_recording:
		return {
			"status": "skipped",
			"reason": "Recording already exists",
			"recording": existing_recording,
		}

	# Check for MP4 recording file
	has_mp4 = any(
		f.get("file_type") == "MP4" and f.get("status") == "completed"
		for f in recording_files
	)

	if not has_mp4:
		frappe.log_error(
			f"No completed MP4 recording found for meeting {meeting_uuid}",
			"Zoom Webhook Warning",
		)
		return {"status": "skipped", "reason": "No MP4 recording available"}

	# Process the recording
	try:
		from lms.lms.doctype.lms_course_recording.lms_course_recording import (
			process_zoom_recording,
		)

		recording_name = process_zoom_recording(live_class_name)

		return {
			"status": "success",
			"recording": recording_name,
			"message": "Recording processing started",
		}

	except Exception as e:
		frappe.log_error(
			f"Failed to process recording for live class {live_class_name}: {str(e)}",
			"Zoom Webhook Error",
		)
		return {"status": "error", "reason": str(e)}
