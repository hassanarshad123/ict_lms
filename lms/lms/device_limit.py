# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime, nowdate


def get_device_id(request=None):
	"""
	Generate a unique device ID from user-agent string only.

	Using only user-agent (not IP) ensures the same browser/device always generates
	the same device_id, even if the user's IP changes (mobile networks, VPN, etc.).
	This prevents the same physical device from being counted multiple times.

	While different users with identical browser versions would technically have
	the same device_id hash, this is acceptable because device_id is always
	used in combination with the user field to identify a specific user's device.

	Args:
		request: Frappe request object (optional, uses frappe.request if not provided)

	Returns:
		str: Hashed device identifier based on user-agent
	"""
	if request is None:
		request = frappe.request

	if not request:
		return None

	user_agent = request.headers.get("User-Agent", "")

	if not user_agent:
		return None

	# Create a hash of user-agent only for stable device identification
	# The same browser on the same device will always produce the same hash
	device_id = hashlib.sha256(user_agent.encode()).hexdigest()[:32]

	return device_id


def get_device_name(request=None):
	"""
	Extract a human-readable device name from the User-Agent string.

	Args:
		request: Frappe request object (optional)

	Returns:
		str: Human-readable device name (e.g., "Chrome on Windows")
	"""
	if request is None:
		request = frappe.request

	if not request:
		return "Unknown Device"

	user_agent = request.headers.get("User-Agent", "")

	if not user_agent:
		return "Unknown Device"

	# Simple browser/OS detection
	browser = "Unknown Browser"
	os_name = "Unknown OS"

	# Detect browser
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

	# Detect OS
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
	"""
	Get the client IP address from the request.

	Args:
		request: Frappe request object (optional)

	Returns:
		str: Client IP address
	"""
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
	# Use get_single_value to avoid caching issues
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

	Args:
		user: User ID (email)
		device_id: Unique device identifier (optional, will be generated if not provided)
		device_name: Human-readable device name (optional)
		ip_address: Client IP address (optional)

	Returns:
		dict: Device document data
	"""
	if not device_id:
		device_id = get_device_id()

	if not device_id:
		return None

	if not device_name:
		device_name = get_device_name()

	if not ip_address:
		ip_address = get_ip_address()

	# Check if device already exists
	existing_device = frappe.db.exists(
		"LMS User Device",
		{"user": user, "device_id": device_id}
	)

	if existing_device:
		# Update last active time
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

	# Create new device record
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


def check_device_limit(user, device_id=None):
	"""
	Check if a user can login from a device (has not exceeded device limit).
	Admins (Moderator, System Manager) are exempt from device limits.

	Args:
		user: User ID (email)
		device_id: Current device ID (optional, will be generated if not provided)

	Returns:
		tuple: (can_login: bool, message: str)
	"""
	settings = get_device_limit_settings()

	if not settings["enabled"]:
		return (True, "")

	# Admins are exempt from device limit
	user_roles = frappe.get_roles(user)
	if "Moderator" in user_roles or "System Manager" in user_roles:
		return (True, "")

	if not device_id:
		device_id = get_device_id()

	if not device_id:
		# If we can't determine device, allow login (graceful degradation)
		return (True, "")

	# Check if device is already registered
	existing_device = frappe.db.exists(
		"LMS User Device",
		{"user": user, "device_id": device_id}
	)

	if existing_device:
		# Device already registered, allow login
		return (True, "")

	# Count current devices for user
	device_count = frappe.db.count(
		"LMS User Device",
		{"user": user}
	)

	if device_count >= settings["limit"]:
		return (
			False,
			_("You have reached the maximum number of devices ({0}). Please contact the administrator to reset your device access.").format(settings["limit"])
		)

	return (True, "")


def get_user_devices(user):
	"""
	Get all registered devices for a user.

	Args:
		user: User ID (email)

	Returns:
		list: List of device documents
	"""
	devices = frappe.get_all(
		"LMS User Device",
		filters={"user": user},
		fields=["name", "device_id", "device_name", "ip_address", "last_active", "creation"],
		order_by="last_active desc"
	)

	# Mark current device
	current_device_id = get_device_id()
	for device in devices:
		device["is_current"] = device["device_id"] == current_device_id

	return devices


def remove_device(user, device_id):
	"""
	Remove a specific device for a user.

	Args:
		user: User ID (email)
		device_id: Device ID to remove

	Returns:
		bool: True if device was removed, False otherwise
	"""
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
	"""
	Remove all devices for a user (admin function).

	Args:
		user: User ID (email)

	Returns:
		int: Number of devices removed
	"""
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
	Remove devices that have been inactive for longer than the stale period.
	This should be run as a scheduled task.

	Returns:
		int: Number of devices removed
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


def check_device_limit_before_session(user):
	"""
	Check device limit BEFORE session is created.
	Called from patched LoginManager.post_login() in lms/__init__.py.
	Throws error immediately if limit exceeded - no session is created.

	Args:
		user: User email/ID
	"""
	try:
		if not user or user == "Guest":
			return

		settings = get_device_limit_settings()

		if not settings["enabled"]:
			return

		# Admins are exempt from device limit
		user_roles = frappe.get_roles(user)
		if "Moderator" in user_roles or "System Manager" in user_roles:
			return

		device_id = get_device_id()
		if not device_id:
			# Can't determine device - allow login (graceful degradation)
			return

		limit = settings["limit"]
		if not limit or limit < 1:
			# Invalid limit - allow login
			return

		# Get all devices for user, ordered by creation (oldest first)
		all_devices = frappe.get_all(
			"LMS User Device",
			filters={"user": user},
			fields=["name", "device_id", "creation"],
			order_by="creation asc"
		)

		# Get the allowed devices (first N registered)
		allowed_device_ids = set(d["device_id"] for d in all_devices[:limit])

		# Check if current device is in the allowed list
		if device_id in allowed_device_ids:
			# Device is allowed - will be updated in on_user_login
			return

		# Check if device is registered but not in allowed list (over limit)
		all_device_ids = set(d["device_id"] for d in all_devices)
		if device_id in all_device_ids:
			# Device registered but not allowed - block login immediately
			frappe.throw(
				_("Device limit exceeded. You already have {0} devices registered. This device is not in the allowed list. Please contact administrator to reset your devices.").format(len(all_devices)),
				frappe.AuthenticationError
			)

		# Device is NOT registered at all
		if len(all_devices) >= limit:
			# At or over limit - block login immediately
			frappe.throw(
				_("Device limit reached. You can only use {0} devices. Please contact administrator to reset your device access.").format(limit),
				frappe.AuthenticationError
			)

		# Under limit - device will be registered in on_user_login hook

	except frappe.AuthenticationError:
		# Re-raise authentication errors (device limit exceeded)
		raise
	except Exception as e:
		# Log error but allow login (don't block due to technical issues)
		frappe.log_error(f"Device limit check failed: {str(e)}", "Device Limit Error")


def on_user_login(login_manager):
	"""
	Hook called on user login AFTER session is created.
	Registers device and updates last_active.
	Device limit check is done in check_device_limit_before_session() BEFORE session creation.

	Args:
		login_manager: Frappe login manager
	"""
	settings = get_device_limit_settings()

	if not settings["enabled"]:
		return

	user = login_manager.user

	if not user or user == "Guest":
		return

	# Admins are exempt
	user_roles = frappe.get_roles(user)
	if "Moderator" in user_roles or "System Manager" in user_roles:
		return

	device_id = get_device_id()
	if not device_id:
		return

	# Check if device is already registered
	existing_device = frappe.db.exists(
		"LMS User Device",
		{"user": user, "device_id": device_id}
	)

	if existing_device:
		# Device already registered, update last_active
		frappe.db.set_value(
			"LMS User Device",
			existing_device,
			"last_active",
			now_datetime(),
			update_modified=False
		)
		frappe.db.commit()
		return

	# Device not registered - register it (limit was already checked before session creation)
	try:
		register_device(user, device_id)
		frappe.db.commit()
	except Exception:
		frappe.log_error("Device registration failed on login")


def validate_device_access():
	"""
	Before request hook to validate device access.
	Only allows the first N registered devices (by creation time).
	Forces logout if user is on a device that's not in the allowed list.
	"""
	# Skip for guest users
	if frappe.session.user == "Guest":
		return

	# Skip for certain paths (login, logout, api auth endpoints)
	if frappe.request:
		path = frappe.request.path or ""
		skip_paths = ["/api/method/login", "/api/method/logout", "/login", "/logout"]
		if any(path.startswith(p) or path == p for p in skip_paths):
			return

	settings = get_device_limit_settings()

	if not settings["enabled"]:
		return

	user = frappe.session.user

	# Admins are exempt from device limit
	user_roles = frappe.get_roles(user)
	if "Moderator" in user_roles or "System Manager" in user_roles:
		return

	try:
		device_id = get_device_id()
		if not device_id:
			return

		limit = settings["limit"]

		# Get all devices for user, ordered by creation (oldest first = first registered)
		all_devices = frappe.get_all(
			"LMS User Device",
			filters={"user": user},
			fields=["name", "device_id", "creation"],
			order_by="creation asc"
		)

		# Get the allowed devices (first N registered)
		allowed_device_ids = set(d["device_id"] for d in all_devices[:limit])

		# Check if current device is in the allowed list
		if device_id in allowed_device_ids:
			# Device is allowed - update last_active
			device_name = frappe.db.get_value(
				"LMS User Device",
				{"user": user, "device_id": device_id},
				"name"
			)
			if device_name:
				frappe.db.set_value(
					"LMS User Device",
					device_name,
					"last_active",
					now_datetime(),
					update_modified=False
				)
			return

		# Device is NOT in allowed list
		# Check if it's registered but over limit
		all_device_ids = set(d["device_id"] for d in all_devices)
		if device_id in all_device_ids:
			# Device is registered but not in the allowed N - force logout
			frappe.local.login_manager.logout()
			frappe.db.commit()
			frappe.throw(
				_("This device has been logged out. You already have {0} other devices registered. Maximum allowed: {0}. Please contact admin to reset.").format(limit),
				frappe.AuthenticationError
			)

		# Device is NOT registered at all
		if len(all_devices) < limit:
			# Under limit - register this new device
			register_device(user, device_id)
			frappe.db.commit()
			return

		# At or over limit with unregistered device - force logout
		frappe.local.login_manager.logout()
		frappe.db.commit()
		frappe.throw(
			_("You have reached the maximum number of devices ({0}). Please contact the administrator to reset your device access.").format(limit),
			frappe.AuthenticationError
		)

	except frappe.AuthenticationError:
		raise
	except Exception:
		# Log error but don't block the request
		frappe.log_error("Device validation failed")


def update_device_activity(user):
	"""
	Update the last active time for the current device.
	Can be called periodically to track device activity.

	Args:
		user: User ID (email)
	"""
	settings = get_device_limit_settings()

	if not settings["enabled"]:
		return

	device_id = get_device_id()
	if not device_id:
		return

	device_name = frappe.db.get_value(
		"LMS User Device",
		{"user": user, "device_id": device_id},
		"name"
	)

	if device_name:
		frappe.db.set_value(
			"LMS User Device",
			device_name,
			"last_active",
			now_datetime()
		)
