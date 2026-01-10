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
		if frappe.session.user == "Administrator":
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
		if "Teacher" in user_roles and action != "read":
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
	if "Teacher" in user_roles:
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
def check_for_new_recordings():
	"""
	Scheduled job to check for new Zoom recordings.
	Acts as fallback if webhook fails.
	Runs hourly.
	"""
	from lms.lms.doctype.lms_vimeo_settings.lms_vimeo_settings import is_vimeo_enabled

	if not is_vimeo_enabled():
		return

	# Find live classes with cloud recording that ended recently
	# and don't have a recording entry yet
	live_classes = frappe.get_all(
		"LMS Live Class",
		filters={
			"auto_recording": "Cloud",
			"date": ["<", frappe.utils.today()],
		},
		fields=["name", "title", "date", "uuid", "batch_name", "host"],
	)

	for live_class in live_classes:
		# Skip if recording already exists
		if frappe.db.exists(
			"LMS Course Recording", {"live_class": live_class.name}
		):
			continue

		# Skip if no UUID (meeting never started)
		if not live_class.uuid:
			continue

		# Try to fetch and process recording
		try:
			process_zoom_recording(live_class.name)
		except Exception as e:
			frappe.log_error(
				f"Failed to process recording for live class {live_class.name}: {str(e)}",
				"Recording Processing Error",
			)


def process_zoom_recording(live_class_name):
	"""
	Fetch recording from Zoom and create LMS Course Recording.
	Enqueues upload job to Vimeo.
	"""
	live_class = frappe.get_doc("LMS Live Class", live_class_name)

	if not live_class.uuid:
		frappe.throw(_("Live class has no meeting UUID"))

	# Get batch and course info
	batch = frappe.get_doc("LMS Batch", live_class.batch_name)
	course = None

	# Get the first course from batch (recordings are linked at course level)
	batch_courses = frappe.get_all(
		"Batch Course", filters={"parent": batch.name}, pluck="course", limit=1
	)
	if batch_courses:
		course = batch_courses[0]
	else:
		frappe.throw(_("Batch {0} has no associated courses").format(batch.name))

	# Create recording entry
	recording = frappe.new_doc("LMS Course Recording")
	recording.title = live_class.title
	recording.course = course
	recording.live_class = live_class_name
	recording.batch = batch.name
	recording.recorded_on = live_class.date
	recording.instructor = live_class.host
	recording.zoom_meeting_uuid = live_class.uuid
	recording.status = "Pending"
	recording.insert(ignore_permissions=True)

	# Enqueue upload job
	frappe.enqueue(
		"lms.lms.doctype.lms_course_recording.recording_upload.process_recording_upload",
		recording_name=recording.name,
		queue="long",
		timeout=3600,  # 1 hour timeout for large files
	)

	return recording.name
