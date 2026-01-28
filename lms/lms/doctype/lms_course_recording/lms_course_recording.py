# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class LMSCourseRecording(Document):
	def validate(self):
		self.validate_course()
		self.set_duration_formatted()

	def validate_course(self):
		"""Ensure course exists"""
		if not frappe.db.exists("LMS Course", self.course):
			frappe.throw(_("Course {0} does not exist").format(self.course))

	def set_duration_formatted(self):
		"""Convert duration in seconds to human-readable format"""
		if self.duration:
			hours = self.duration // 3600
			minutes = (self.duration % 3600) // 60
			seconds = self.duration % 60

			parts = []
			if hours:
				parts.append(f"{hours}h")
			if minutes:
				parts.append(f"{minutes}m")
			if seconds and not hours:
				parts.append(f"{seconds}s")

			self.duration_formatted = " ".join(parts) if parts else "0s"

	def before_insert(self):
		self.enforce_role_permissions("create")

	def before_save(self):
		if not self.is_new():
			self.enforce_role_permissions("write")

	def on_trash(self):
		self.enforce_role_permissions("delete")

	def enforce_role_permissions(self, action):
		"""Enforce role-based permissions for recording management"""
		# Skip permission check for system/background operations
		if frappe.flags.in_install or frappe.flags.in_migrate:
			return

		# Skip if called with ignore_permissions (e.g., from background jobs via vimeo_processor)
		if self.flags.get("ignore_permissions"):
			return

		if frappe.session.user == "Administrator":
			return

		# Guest user in background job context - allow if processing recordings
		if frappe.session.user == "Guest":
			# This happens when Vimeo webhook triggers background job
			# The job runs as Guest but should be allowed to create recordings
			return

		user_roles = frappe.get_roles(frappe.session.user)

		# Moderator (Admin) can do anything
		if "Moderator" in user_roles:
			return

		# Course Creator can manage recordings for their courses
		if "Course Creator" in user_roles:
			if self.is_course_instructor():
				return

		# Teacher cannot create/edit/delete recordings
		if "LMS Teacher" in user_roles and action != "read":
			frappe.throw(
				_("Teachers do not have permission to {0} recordings").format(action),
				frappe.PermissionError,
			)

		frappe.throw(
			_("You do not have permission to {0} this recording").format(action),
			frappe.PermissionError,
		)

	def is_course_instructor(self):
		"""Check if current user is an instructor for the recording's course"""
		return frappe.db.exists(
			"Course Instructor",
			{"parent": self.course, "instructor": frappe.session.user},
		)


def has_recording_access(recording_name, user=None):
	"""
	Check if a user has access to view a recording.
	Returns True if user is:
	- Administrator
	- Moderator
	- Course instructor
	- Teacher assigned to a batch with this course
	- Enrolled student
	"""
	if not user:
		user = frappe.session.user

	if user == "Administrator":
		return True

	recording = frappe.get_doc("LMS Course Recording", recording_name)
	user_roles = frappe.get_roles(user)

	# Moderator has full access
	if "Moderator" in user_roles:
		return True

	# Course instructor has access
	if frappe.db.exists(
		"Course Instructor", {"parent": recording.course, "instructor": user}
	):
		return True

	# Teacher assigned to a batch with this course
	if "LMS Teacher" in user_roles:
		# Check if user is instructor on any batch that includes this course
		batches_with_course = frappe.get_all(
			"Batch Course", filters={"course": recording.course}, pluck="parent"
		)
		for batch in batches_with_course:
			if frappe.db.exists(
				"Course Instructor",
				{
					"parenttype": "LMS Batch",
					"parent": batch,
					"instructor": user,
				},
			):
				return True

	# Enrolled student has access
	if frappe.db.exists(
		"LMS Enrollment", {"course": recording.course, "member": user}
	):
		return True

	return False


@frappe.whitelist()
def trigger_vimeo_poll():
	"""
	Manually trigger Vimeo folder polling for new recordings.
	Only available to admins.
	"""
	if not frappe.has_permission("LMS Course Recording", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from lms.lms.doctype.lms_course_recording.vimeo_processor import poll_vimeo_folder
	poll_vimeo_folder()
	return {"status": "success", "message": "Vimeo polling triggered"}
