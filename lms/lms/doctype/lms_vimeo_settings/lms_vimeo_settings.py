# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from frappe.model.document import Document


class LMSVimeoSettings(Document):
	def validate(self):
		if self.enabled:
			self.validate_credentials()
			self.validate_embed_whitelist()

	def validate_credentials(self):
		"""Test Vimeo API credentials by making a simple API call"""
		if not self.access_token:
			return

		try:
			response = requests.get(
				"https://api.vimeo.com/me",
				headers={
					"Authorization": f"Bearer {self.get_password('access_token')}",
					"Accept": "application/vnd.vimeo.*+json;version=3.4",
				},
				timeout=10,
			)
			if response.status_code != 200:
				frappe.throw(
					_("Invalid Vimeo credentials. Please check your access token. Error: {0}").format(
						response.json().get("error", "Unknown error")
					)
				)
		except requests.exceptions.RequestException as e:
			frappe.throw(_("Failed to connect to Vimeo API: {0}").format(str(e)))

	def validate_embed_whitelist(self):
		"""Ensure embed whitelist has at least one valid domain"""
		if not self.embed_whitelist:
			frappe.throw(_("At least one embed whitelist domain is required"))

		domains = [d.strip() for d in self.embed_whitelist.split(",") if d.strip()]
		if not domains:
			frappe.throw(_("At least one valid embed whitelist domain is required"))


def get_vimeo_settings():
	"""Get Vimeo settings if enabled"""
	settings = frappe.get_single("LMS Vimeo Settings")
	if not settings.enabled:
		return None
	return settings


def is_vimeo_enabled():
	"""Check if Vimeo integration is enabled"""
	return frappe.db.get_single_value("LMS Vimeo Settings", "enabled")
