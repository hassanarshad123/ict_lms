# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

"""
Scheduler tasks for time-limited batch enrollment management.
These tasks handle automatic expiration of enrollments and sending reminder emails.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate


def expire_batch_enrollments():
	"""
	Daily task to expire time-limited batch enrollments that have passed their access end date.
	This task:
	1. Finds all active time-limited enrollments where access_end_date < today
	2. Updates their status to 'Expired'
	3. Removes course enrollments and live class access
	4. Optionally sends expiry notification email
	"""
	today = getdate(nowdate())

	# Get all active time-limited enrollments that have expired
	expired_enrollments = frappe.get_all(
		"LMS Batch Enrollment",
		filters={
			"is_time_limited": 1,
			"status": ["in", ["Active", "Extended"]],
			"access_end_date": ["<", today]
		},
		fields=["name", "member", "member_name", "batch", "access_end_date"]
	)

	expired_count = 0
	error_count = 0

	for enrollment_data in expired_enrollments:
		try:
			enrollment = frappe.get_doc("LMS Batch Enrollment", enrollment_data.name)
			enrollment.mark_as_expired()
			expired_count += 1

			# Send expiry notification
			try:
				send_expiry_notification(enrollment_data)
			except Exception as e:
				frappe.log_error(
					message=f"Failed to send expiry notification for enrollment {enrollment_data.name}: {str(e)}",
					title="Enrollment Expiry Notification Error"
				)

		except Exception as e:
			error_count += 1
			frappe.log_error(
				message=f"Failed to expire enrollment {enrollment_data.name}: {str(e)}",
				title="Enrollment Expiry Error"
			)

	if expired_count > 0 or error_count > 0:
		frappe.logger().info(
			f"Batch Enrollment Expiry: Expired {expired_count} enrollments, {error_count} errors"
		)

	return {
		"expired": expired_count,
		"errors": error_count
	}


def send_expiry_reminders():
	"""
	Daily task to send reminder emails to students whose access is about to expire.
	Sends reminders at 7 days, 3 days, and 1 day before expiry.
	"""
	today = getdate(nowdate())
	reminder_days = [7, 3, 1]

	total_sent = 0
	errors = 0

	for days in reminder_days:
		expiry_date = add_days(today, days)

		# Get enrollments expiring on this date
		enrollments = frappe.get_all(
			"LMS Batch Enrollment",
			filters={
				"is_time_limited": 1,
				"status": ["in", ["Active", "Extended"]],
				"access_end_date": expiry_date
			},
			fields=["name", "member", "member_name", "batch", "access_end_date"]
		)

		for enrollment_data in enrollments:
			try:
				send_expiry_reminder(enrollment_data, days)
				total_sent += 1
			except Exception as e:
				errors += 1
				frappe.log_error(
					message=f"Failed to send {days}-day expiry reminder for enrollment {enrollment_data.name}: {str(e)}",
					title="Expiry Reminder Error"
				)

	if total_sent > 0 or errors > 0:
		frappe.logger().info(
			f"Batch Enrollment Reminders: Sent {total_sent} reminders, {errors} errors"
		)

	return {
		"sent": total_sent,
		"errors": errors
	}


def send_expiry_reminder(enrollment_data, days_remaining):
	"""
	Send an expiry reminder email to the student.

	Args:
		enrollment_data: Dict containing enrollment details
		days_remaining: Number of days until expiry
	"""
	# Check if email account is configured
	outgoing_email_account = frappe.get_cached_value(
		"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
	)

	if not outgoing_email_account and not frappe.conf.get("mail_login"):
		return

	# Get batch details
	batch = frappe.db.get_value(
		"LMS Batch",
		enrollment_data.batch,
		["name", "title"],
		as_dict=True
	)

	if not batch:
		return

	# Prepare email
	if days_remaining == 1:
		subject = _("Your access to {0} expires tomorrow").format(batch.title)
		urgency = "tomorrow"
	else:
		subject = _("Your access to {0} expires in {1} days").format(batch.title, days_remaining)
		urgency = _("{0} days").format(days_remaining)

	message = _("""
Dear {student_name},

This is a reminder that your access to the batch "{batch_title}" will expire in {urgency}.

Access End Date: {access_end_date}

If you would like to continue learning, please contact the administrator to extend your access.

Best regards,
The Learning Team
	""").format(
		student_name=enrollment_data.member_name or enrollment_data.member,
		batch_title=batch.title,
		urgency=urgency,
		access_end_date=str(enrollment_data.access_end_date)
	)

	frappe.sendmail(
		recipients=enrollment_data.member,
		subject=subject,
		message=message,
		header=[_("Access Expiry Reminder"), "orange"],
		retry=3,
	)


def send_expiry_notification(enrollment_data):
	"""
	Send a notification email when enrollment has expired.

	Args:
		enrollment_data: Dict containing enrollment details
	"""
	# Check if email account is configured
	outgoing_email_account = frappe.get_cached_value(
		"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
	)

	if not outgoing_email_account and not frappe.conf.get("mail_login"):
		return

	# Get batch details
	batch = frappe.db.get_value(
		"LMS Batch",
		enrollment_data.batch,
		["name", "title"],
		as_dict=True
	)

	if not batch:
		return

	subject = _("Your access to {0} has expired").format(batch.title)

	message = _("""
Dear {student_name},

Your access to the batch "{batch_title}" has expired as of {access_end_date}.

If you would like to regain access and continue learning, please contact the administrator to extend your enrollment.

Thank you for being part of our learning community.

Best regards,
The Learning Team
	""").format(
		student_name=enrollment_data.member_name or enrollment_data.member,
		batch_title=batch.title,
		access_end_date=str(enrollment_data.access_end_date)
	)

	frappe.sendmail(
		recipients=enrollment_data.member,
		subject=subject,
		message=message,
		header=[_("Access Expired"), "red"],
		retry=3,
	)


def get_enrollment_statistics():
	"""
	Get statistics about time-limited enrollments.
	Useful for reporting and monitoring.

	Returns:
		dict: Statistics about enrollments
	"""
	today = getdate(nowdate())

	# Total time-limited enrollments
	total = frappe.db.count("LMS Batch Enrollment", {"is_time_limited": 1})

	# Active enrollments
	active = frappe.db.count(
		"LMS Batch Enrollment",
		{"is_time_limited": 1, "status": ["in", ["Active", "Extended"]]}
	)

	# Expired enrollments
	expired = frappe.db.count(
		"LMS Batch Enrollment",
		{"is_time_limited": 1, "status": "Expired"}
	)

	# Manually removed
	removed = frappe.db.count(
		"LMS Batch Enrollment",
		{"is_time_limited": 1, "status": "Manually Removed"}
	)

	# Expiring in next 7 days
	expiry_date = add_days(today, 7)
	expiring_soon = frappe.db.count(
		"LMS Batch Enrollment",
		{
			"is_time_limited": 1,
			"status": ["in", ["Active", "Extended"]],
			"access_end_date": ["between", [today, expiry_date]]
		}
	)

	# Extended enrollments (total extensions)
	extended = frappe.db.count(
		"LMS Batch Enrollment",
		{"is_time_limited": 1, "extended_count": [">", 0]}
	)

	return {
		"total_time_limited": total,
		"active": active,
		"expired": expired,
		"manually_removed": removed,
		"expiring_in_7_days": expiring_soon,
		"enrollments_with_extensions": extended
	}
