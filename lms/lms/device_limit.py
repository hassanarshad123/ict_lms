# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime, nowdate


def _normalize_user_agent(user_agent):
	"""
	Strip version numbers from User-Agent so browser updates don't change the hash.

	'Chrome/144.0.0.0' and 'Chrome/145.0.0.0' both normalize to 'Chrome',
	while OS info like '(Windows NT 10.0; Win64; x64)' stays intact.
	"""
	return re.sub(r"/\S+", "", user_agent).strip()


def get_device_id(request=None):
	"""
	Generate a stable device ID from a normalized user-agent string.

	Version numbers are stripped before hashing so a Chrome auto-update
	(e.g. 144 -> 145) does NOT change the device fingerprint.

	The hash is always used together with the user field, so two different
	users on the same browser/OS will not collide.
	"""
	if request is None:
		request = frappe.request

	if not request:
		return None

	user_agent = request.headers.get("User-Agent", "")

	if not user_agent:
		return None

	normalized = _normalize_user_agent(user_agent)
	return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _get_legacy_device_id(request=None):
	"""
	Device ID using the OLD algorithm (raw UA hash, no normalization).
	Used only during migration: if a device was registered with the old hash,
	we recognize it and silently update the stored hash to the new format.
	"""
	if request is None:
		request = frappe.request

	if not request:
		return None

	user_agent = request.headers.get("User-Agent", "")

	if not user_agent:
		return None

	return hashlib.sha256(user_agent.encode()).hexdigest()[:32]


def get_device_name(request=None):
	"""
	Extract a human-readable device name from the User-Agent string.

	Returns:
		str: e.g. "Chrome on Windows"
	"""
	if request is None:
		request = frappe.request

	if not request:
		return "Unknown Device"

	user_agent = request.headers.get("User-Agent", "")

	if not user_agent:
		return "Unknown Device"

	browser = "Unknown Browser"
	os_name = "Unknown OS"

	if "Chrome" in user_agent and "Edg" not in user_agent:
		browser = "Chrome"
	elif "Firefox" in user_agent:
		browser = "Firefox"
	elif "Safari" in user_agent and "Chrome" not in user_agent:
		browser = "Safari"
	elif "Edg" in user_agent:
		browser = "Edge"
	elif "MSIE" in user_agent or "Trident" in user_agent:
		browser = "Internet Explorer"
	elif "Opera" in user_agent or "OPR" in user_agent:
		browser = "Opera"

	if "Windows" in user_agent:
		os_name = "Windows"
	elif "Mac OS" in user_agent or "Macintosh" in user_agent:
		os_name = "macOS"
	elif "Linux" in user_agent and "Android" not in user_agent:
		os_name = "Linux"
	elif "Android" in user_agent:
		os_name = "Android"
	elif "iPhone" in user_agent or "iPad" in user_agent:
		os_name = "iOS"

	return f"{browser} on {os_name}"


def get_ip_address(request=None):
	"""Get the client IP address from the request."""
	if request is None:
		request = frappe.request

	if not request:
		return None

	ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "")
	if ip_address and "," in ip_address:
		ip_address = ip_address.split(",")[0].strip()

	return ip_address


def get_device_limit_settings():
	"""
	Get device limit settings from LMS Settings.

	Returns:
		dict: Settings with keys: enabled, limit, stale_days
	"""
	enabled = frappe.db.get_single_value("LMS Settings", "enable_device_limit") or 0
	limit = frappe.db.get_single_value("LMS Settings", "device_limit") or 2
	stale_days = frappe.db.get_single_value("LMS Settings", "device_stale_days") or 30

	return {
		"enabled": enabled,
		"limit": limit,
		"stale_days": stale_days,
	}


def register_device(user, device_id=None, device_name=None, ip_address=None):
	"""
	Register or update a device for a user.

	Returns:
		Document | None: The device document, or None if device_id unavailable
	"""
	if not device_id:
		device_id = get_device_id()

	if not device_id:
		return None

	if not device_name:
		device_name = get_device_name()

	if not ip_address:
		ip_address = get_ip_address()

	existing_device = frappe.db.exists(
		"LMS User Device",
		{"user": user, "device_id": device_id}
	)

	if existing_device:
		frappe.db.set_value(
			"LMS User Device",
			existing_device,
			{
				"last_active": now_datetime(),
				"ip_address": ip_address,
				"device_name": device_name,
			}
		)
		return frappe.get_doc("LMS User Device", existing_device)

	device = frappe.get_doc({
		"doctype": "LMS User Device",
		"user": user,
		"device_id": device_id,
		"device_name": device_name,
		"ip_address": ip_address,
		"last_active": now_datetime(),
	})
	device.flags.ignore_permissions = True
	device.insert()

	return device


def get_user_devices(user):
	"""Get all registered devices for a user, with current device marked."""
	devices = frappe.get_all(
		"LMS User Device",
		filters={"user": user},
		fields=["name", "device_id", "device_name", "ip_address", "last_active", "creation"],
		order_by="last_active desc"
	)

	current_device_id = get_device_id()
	for device in devices:
		device["is_current"] = device["device_id"] == current_device_id

	return devices


def remove_device(user, device_id):
	"""Remove a specific device for a user."""
	device_name = frappe.db.get_value(
		"LMS User Device",
		{"user": user, "device_id": device_id},
		"name"
	)

	if device_name:
		frappe.delete_doc("LMS User Device", device_name, ignore_permissions=True)
		return True

	return False


def clear_all_devices(user):
	"""Remove all devices for a user (admin function)."""
	devices = frappe.get_all(
		"LMS User Device",
		filters={"user": user},
		pluck="name"
	)

	for device in devices:
		frappe.delete_doc("LMS User Device", device, ignore_permissions=True)

	return len(devices)


def cleanup_stale_devices():
	"""
	Remove devices inactive longer than the stale period.
	Runs as a daily scheduled task.
	"""
	settings = get_device_limit_settings()

	if not settings["enabled"]:
		return 0

	stale_date = add_days(nowdate(), -settings["stale_days"])

	stale_devices = frappe.get_all(
		"LMS User Device",
		filters={"last_active": ["<", stale_date]},
		pluck="name"
	)

	for device in stale_devices:
		frappe.delete_doc("LMS User Device", device, ignore_permissions=True)

	if stale_devices:
		frappe.db.commit()

	return len(stale_devices)


# ---------------------------------------------------------------------------
# Login-time enforcement
# ---------------------------------------------------------------------------


def check_device_limit_before_session(user):
	"""
	Check device limit BEFORE session is created.
	Called from patched LoginManager.post_login() in lms/__init__.py.
	Throws AuthenticationError immediately if limit exceeded — no session is created.
	"""
	try:
		if not user or user == "Guest":
			return

		settings = get_device_limit_settings()

		if not settings["enabled"]:
			return

		user_roles = frappe.get_roles(user)
		if "Moderator" in user_roles or "System Manager" in user_roles:
			return

		device_id = get_device_id()
		if not device_id:
			return

		legacy_device_id = _get_legacy_device_id()

		limit = settings["limit"]
		if not limit or limit < 1:
			return

		all_devices = frappe.get_all(
			"LMS User Device",
			filters={"user": user},
			fields=["name", "device_id", "creation"],
			order_by="creation asc"
		)

		allowed_device_ids = set(d["device_id"] for d in all_devices[:limit])
		all_device_ids = set(d["device_id"] for d in all_devices)

		# Check new hash
		if device_id in allowed_device_ids:
			return

		# Check legacy hash (device registered before UA normalization)
		if legacy_device_id and legacy_device_id != device_id and legacy_device_id in allowed_device_ids:
			return

		# Device is registered but NOT in the allowed first-N
		is_registered = device_id in all_device_ids
		is_legacy_registered = legacy_device_id and legacy_device_id != device_id and legacy_device_id in all_device_ids
		if is_registered or is_legacy_registered:
			frappe.throw(
				_("Device limit exceeded. You already have {0} devices registered. This device is not in the allowed list. Please contact administrator to reset your devices.").format(len(all_devices)),
				frappe.AuthenticationError
			)

		# Device is NOT registered at all
		if len(all_devices) >= limit:
			frappe.throw(
				_("Device limit reached. You can only use {0} devices. Please contact administrator to reset your device access.").format(limit),
				frappe.AuthenticationError
			)

		# Under limit — device will be registered in on_user_login hook

	except frappe.AuthenticationError:
		raise
	except Exception as e:
		# Log but don't block login due to technical issues
		frappe.log_error(f"Device limit check failed: {str(e)}", "Device Limit Error")


def on_user_login(login_manager):
	"""
	Hook called on user login AFTER session is created.
	Registers the device and migrates legacy hashes to the new format.
	"""
	try:
		settings = get_device_limit_settings()

		if not settings["enabled"]:
			return

		user = login_manager.user

		if not user or user == "Guest":
			return

		user_roles = frappe.get_roles(user)
		if "Moderator" in user_roles or "System Manager" in user_roles:
			return

		device_id = get_device_id()
		if not device_id:
			return

		# 1. Device already exists with new hash — just update last_active
		existing = frappe.db.exists(
			"LMS User Device",
			{"user": user, "device_id": device_id}
		)

		if existing:
			frappe.db.set_value(
				"LMS User Device",
				existing,
				"last_active",
				now_datetime(),
				update_modified=False
			)
			frappe.db.commit()
			return

		# 2. Check if device exists with the legacy (pre-normalization) hash
		legacy_device_id = _get_legacy_device_id()
		if legacy_device_id and legacy_device_id != device_id:
			legacy_device = frappe.db.exists(
				"LMS User Device",
				{"user": user, "device_id": legacy_device_id}
			)
			if legacy_device:
				# Migrate: swap old hash for new hash so future logins match instantly
				frappe.db.set_value(
					"LMS User Device",
					legacy_device,
					{
						"device_id": device_id,
						"last_active": now_datetime(),
						"device_name": get_device_name(),
						"ip_address": get_ip_address(),
					}
				)
				frappe.db.commit()
				return

		# 3. Brand-new device — register it (limit was already checked before session creation)
		register_device(user, device_id)
		frappe.db.commit()

	except Exception:
		frappe.log_error("Device registration failed on login")
