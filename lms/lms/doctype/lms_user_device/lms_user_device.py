# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class LMSUserDevice(Document):
	def before_insert(self):
		self.last_active = now_datetime()

	def validate(self):
		self.validate_duplicate_device()

	def validate_duplicate_device(self):
		"""Ensure device_id is unique per user"""
		if frappe.db.exists(
			"LMS User Device",
			{
				"user": self.user,
				"device_id": self.device_id,
				"name": ["!=", self.name]
			}
		):
			frappe.throw(_("This device is already registered for this user."))

	def update_last_active(self):
		"""Update the last active timestamp"""
		self.last_active = now_datetime()
		self.save(ignore_permissions=True)
