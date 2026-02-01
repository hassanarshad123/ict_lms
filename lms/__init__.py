__version__ = "2.44.0"

import frappe
from frappe.auth import LoginManager


# Store the original post_login method
_original_post_login = LoginManager.post_login


def _patched_post_login(self):
	"""
	Patched post_login that checks device limit BEFORE creating session.
	This prevents session creation entirely if device limit is exceeded.
	"""
	from lms.lms.device_limit import check_device_limit_before_session

	# Check device limit before creating session
	check_device_limit_before_session(self.user)

	# Call original method if check passed
	_original_post_login(self)


# Apply the monkey-patch
LoginManager.post_login = _patched_post_login
