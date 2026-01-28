# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.email.doctype.email_template.email_template import get_email_template
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime, nowdate


class LMSBatchEnrollment(Document):
	def before_insert(self):
		# Set enrollment date if not set
		if not self.enrollment_date:
			self.enrollment_date = nowdate()

		# Set access start date if not set
		if not self.access_start_date:
			self.access_start_date = self.enrollment_date

		# Calculate access end date if time-limited and duration is provided
		if self.is_time_limited and self.access_duration_days and not self.access_end_date:
			self.access_end_date = add_days(self.access_start_date, self.access_duration_days)

		# Initialize status
		if not self.status:
			self.status = "Active"

	def after_insert(self):
		send_confirmation_email(self)
		self.add_member_to_live_class()

	def validate(self):
		self.validate_owner()
		self.validate_duplicate_members()
		self.validate_payment()
		self.validate_self_enrollment()
		self.validate_seat_availability()
		self.validate_course_enrollment()
		self.validate_time_limited_fields()
		self.validate_dates()

	def validate_time_limited_fields(self):
		"""Validate time-limited enrollment fields"""
		if self.is_time_limited:
			if not self.access_end_date and not self.access_duration_days:
				frappe.throw(_("For time-limited enrollments, either Access End Date or Access Duration (Days) is required."))

			# Calculate access_end_date from duration if not provided
			if self.access_duration_days and not self.access_end_date:
				if not self.access_start_date:
					self.access_start_date = nowdate()
				self.access_end_date = add_days(self.access_start_date, self.access_duration_days)

			# Calculate duration from dates if not provided
			if self.access_end_date and not self.access_duration_days:
				if not self.access_start_date:
					self.access_start_date = nowdate()
				self.access_duration_days = (getdate(self.access_end_date) - getdate(self.access_start_date)).days

	def validate_dates(self):
		"""Validate date fields"""
		if self.access_start_date and self.access_end_date:
			if getdate(self.access_end_date) < getdate(self.access_start_date):
				frappe.throw(_("Access End Date cannot be before Access Start Date."))

	def validate_owner(self):
		if self.owner == self.member:
			return

		roles = frappe.get_roles(self.owner)
		allowed_roles = {"Moderator", "Batch Evaluator", "Course Creator"}
		if not allowed_roles.intersection(roles):
			frappe.throw(_("You must be a Moderator, Course Creator, or Batch Evaluator to enroll users in a batch."))

	def validate_payment(self):
		paid_batch = frappe.db.get_value("LMS Batch", self.batch, "paid_batch")
		if paid_batch:
			payment = frappe.db.exists(
				"LMS Payment",
				{
					"payment_for_document_type": "LMS Batch",
					"payment_for_document": self.batch,
					"member": self.member,
					"payment_received": True,
				},
			)
			if not payment:
				frappe.throw(_("Payment is required to enroll in this batch."))
			else:
				self.payment = payment

	def validate_self_enrollment(self):
		batch_details = frappe.db.get_value(
			"LMS Batch", self.batch, ["allow_self_enrollment", "paid_batch"], as_dict=True
		)
		if batch_details.paid_batch:
			return
		if not batch_details.allow_self_enrollment and not self.is_admin():
			frappe.throw(_("Enrollment in this batch is restricted. Please contact the Administrator."))

	def is_admin(self):
		roles = frappe.get_roles(frappe.session.user)
		return any(r in roles for r in ["Course Creator", "Moderator", "Batch Evaluator"])

	def validate_duplicate_members(self):
		if frappe.db.exists(
			"LMS Batch Enrollment",
			{"batch": self.batch, "member": self.member, "name": ["!=", self.name]},
		):
			frappe.throw(_("Member already enrolled in this batch"))

	def validate_seat_availability(self):
		seat_count = frappe.db.get_value("LMS Batch", self.batch, "seat_count")
		enrolled_count = frappe.db.count("LMS Batch Enrollment", {"batch": self.batch})
		if seat_count and enrolled_count >= seat_count:
			frappe.throw(_("There are no seats available in this batch."))

	def validate_course_enrollment(self):
		courses = frappe.get_all("Batch Course", filters={"parent": self.batch}, fields=["course"])

		for course in courses:
			if not frappe.db.exists(
				"LMS Enrollment",
				{"course": course.course, "member": self.member},
			):
				enrollment = frappe.new_doc("LMS Enrollment")
				enrollment.course = course.course
				enrollment.member = self.member
				enrollment.enrollment_from_batch = self.batch
				enrollment.save()

	def add_member_to_live_class(self):
		live_classes = frappe.get_all("LMS Live Class", {"batch_name": self.batch}, ["name", "event"])

		for live_class in live_classes:
			if live_class.event:
				frappe.get_doc(
					{
						"doctype": "Event Participants",
						"reference_doctype": "User",
						"reference_docname": self.member,
						"email": self.member,
						"parent": live_class.event,
						"parenttype": "Event",
						"parentfield": "event_participants",
					}
				).save()

	def on_trash(self):
		"""Remove course enrollments and live class participation when batch enrollment is deleted."""
		self.remove_course_enrollments()
		self.remove_member_from_live_class()

	def remove_course_enrollments(self):
		"""Delete LMS Enrollment records that were created from this batch enrollment."""
		enrollments = frappe.get_all(
			"LMS Enrollment",
			filters={
				"enrollment_from_batch": self.batch,
				"member": self.member
			},
			pluck="name"
		)

		for enrollment in enrollments:
			frappe.delete_doc("LMS Enrollment", enrollment, ignore_permissions=True)

	def remove_member_from_live_class(self):
		"""Remove member from live class events when batch enrollment is deleted."""
		live_classes = frappe.get_all("LMS Live Class", {"batch_name": self.batch}, ["name", "event"])

		for live_class in live_classes:
			if live_class.event:
				participants = frappe.get_all(
					"Event Participants",
					filters={
						"parent": live_class.event,
						"reference_doctype": "User",
						"reference_docname": self.member
					},
					pluck="name"
				)
				for participant in participants:
					frappe.delete_doc("Event Participants", participant, ignore_permissions=True)

	def has_active_access(self):
		"""Check if the enrollment has active access"""
		if self.status in ["Expired", "Manually Removed"]:
			return False

		if not self.is_time_limited:
			return True

		if self.access_end_date and getdate(self.access_end_date) < getdate(nowdate()):
			return False

		return True

	def extend_access(self, extension_days, reason=None, extended_by=None):
		"""Extend the enrollment access by specified days"""
		if not self.is_time_limited:
			frappe.throw(_("Cannot extend access for non-time-limited enrollments."))

		if not extension_days or extension_days <= 0:
			frappe.throw(_("Extension days must be a positive number."))

		previous_end_date = self.access_end_date

		# Calculate new end date
		# If already expired, extend from today; otherwise extend from current end date
		if self.access_end_date and getdate(self.access_end_date) < getdate(nowdate()):
			new_end_date = add_days(nowdate(), extension_days)
		else:
			new_end_date = add_days(self.access_end_date or nowdate(), extension_days)

		# Update fields
		self.access_end_date = new_end_date
		self.extended_count = (self.extended_count or 0) + 1
		self.last_extended_on = now_datetime()
		self.status = "Extended"

		# Update total duration
		if self.access_start_date:
			self.access_duration_days = (getdate(new_end_date) - getdate(self.access_start_date)).days

		# Add to extension history
		self.append("extension_history", {
			"extended_on": now_datetime(),
			"extended_by": extended_by or frappe.session.user,
			"previous_end_date": previous_end_date,
			"new_end_date": new_end_date,
			"extension_days": extension_days,
			"reason": reason
		})

		self.save()

		return {
			"success": True,
			"previous_end_date": str(previous_end_date) if previous_end_date else None,
			"new_end_date": str(new_end_date),
			"extended_count": self.extended_count
		}

	def mark_as_expired(self):
		"""Mark enrollment as expired"""
		if self.status != "Expired":
			self.status = "Expired"
			self.save()

			# Remove course enrollments and live class access
			self.remove_course_enrollments()
			self.remove_member_from_live_class()

	def remove_from_batch(self, reason=None):
		"""Manually remove student from batch"""
		self.status = "Manually Removed"
		self.removal_reason = reason
		self.save()

		# Remove course enrollments and live class access
		self.remove_course_enrollments()
		self.remove_member_from_live_class()


@frappe.whitelist()
def send_confirmation_email(doc):
	if isinstance(doc, str):
		doc = frappe._dict(json.loads(doc))

	if not doc.confirmation_email_sent:
		outgoing_email_account = frappe.get_cached_value(
			"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
		)
		if not doc.confirmation_email_sent and (outgoing_email_account or frappe.conf.get("mail_login")):
			send_mail(doc)
			frappe.db.set_value(doc.doctype, doc.name, "confirmation_email_sent", 1)


def send_mail(doc):
	batch = frappe.db.get_value(
		"LMS Batch",
		doc.batch,
		[
			"name",
			"title",
			"start_date",
			"start_time",
			"medium",
			"confirmation_email_template",
		],
		as_dict=1,
	)

	subject = _("Enrollment Confirmation for {0}").format(batch.title)
	template = "batch_confirmation"
	custom_template = batch.confirmation_email_template or frappe.db.get_single_value(
		"LMS Settings", "batch_confirmation_template"
	)

	args = {
		"title": batch.title,
		"student_name": doc.member_name,
		"start_time": batch.start_time,
		"start_date": batch.start_date,
		"medium": batch.medium,
		"name": batch.name,
	}

	# Add time-limited access info if applicable
	if doc.get("is_time_limited") and doc.get("access_end_date"):
		args["access_end_date"] = doc.access_end_date
		args["is_time_limited"] = True

	if custom_template:
		email_template = get_email_template(custom_template, args)
		subject = email_template.get("subject")
		content = email_template.get("message")

	frappe.sendmail(
		recipients=doc.member,
		subject=subject,
		template=template if not custom_template else None,
		content=content if custom_template else None,
		args=args,
		header=[_(batch.title), "green"],
		retry=3,
	)


def check_batch_access(user, batch):
	"""Check if user has active access to a batch"""
	enrollment = frappe.db.get_value(
		"LMS Batch Enrollment",
		{"member": user, "batch": batch},
		["name", "is_time_limited", "status", "access_end_date"],
		as_dict=True
	)

	if not enrollment:
		return False

	if enrollment.status in ["Expired", "Manually Removed"]:
		return False

	if not enrollment.is_time_limited:
		return True

	if enrollment.access_end_date and getdate(enrollment.access_end_date) < getdate(nowdate()):
		# Auto-expire if past end date
		frappe.db.set_value("LMS Batch Enrollment", enrollment.name, "status", "Expired")
		return False

	return True
