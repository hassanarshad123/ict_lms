"""API methods for the LMS."""

import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import timedelta
from xml.dom.minidom import parseString

import frappe
from frappe import _
from frappe.integrations.frappe_providers.frappecloud_billing import (
	current_site_info,
	is_fc_site,
)
from frappe.query_builder import DocType
from frappe.translate import get_all_translations
from frappe.utils import (
	add_days,
	cint,
	date_diff,
	flt,
	format_date,
	get_datetime,
	getdate,
	now,
	nowdate,
)
from frappe.utils.response import Response

from lms.lms.doctype.course_lesson.course_lesson import save_progress
from lms.lms.utils import get_average_rating, get_batch_details, get_course_details, get_lesson_count


@frappe.whitelist(allow_guest=True)
def get_user_info():
	if frappe.session.user == "Guest":
		return None

	user = frappe.db.get_value(
		"User",
		frappe.session.user,
		["name", "email", "enabled", "user_image", "full_name", "user_type", "username"],
		as_dict=1,
	)
	user["roles"] = frappe.get_roles(user.name)

	# New 4-role model flags
	user.is_admin = "Moderator" in user.roles  # Admin = Moderator
	user.is_course_creator = "Course Creator" in user.roles
	user.is_teacher = "Teacher" in user.roles
	user.is_student = "LMS Student" in user.roles

	# Legacy flags for backward compatibility (mapped to new roles)
	user.is_moderator = user.is_admin  # Moderator = Admin
	user.is_instructor = user.is_course_creator  # Instructor = Course Creator
	user.is_evaluator = "Batch Evaluator" in user.roles  # Keep for backward compatibility

	# Computed permission flags
	user.can_create = user.is_admin or user.is_course_creator  # Can create courses/batches
	user.can_manage_roles = user.is_admin  # Only Admin can manage roles

	user.is_fc_site = is_fc_site()
	user.is_system_manager = "System Manager" in user.roles
	user.sitename = frappe.local.site
	user.developer_mode = frappe.conf.developer_mode
	if user.is_fc_site and user.is_system_manager:
		user.site_info = current_site_info()
	return user


@frappe.whitelist(allow_guest=True, methods=["POST"])
def api_login(usr, pwd):
	"""
	API login endpoint for token-based authentication.
	Returns api_key and api_secret for use with Authorization header.

	Args:
		usr: User email or username
		pwd: User password

	Returns:
		dict: Contains api_key, api_secret, and user info on success

	Usage:
		POST /api/method/lms.lms.api.api_login
		Body: {"usr": "user@example.com", "pwd": "password123"}

		Then use token for authenticated requests:
		Authorization: token <api_key>:<api_secret>
	"""
	from frappe.utils.password import check_password as validate_password

	# Validate required fields
	if not usr:
		frappe.throw(_("Email or username is required"))
	if not pwd:
		frappe.throw(_("Password is required"))

	# Validate credentials
	try:
		user = validate_password(usr, pwd)
	except frappe.AuthenticationError:
		frappe.throw(_("Invalid email or password"), frappe.AuthenticationError)

	# Get user document
	user_doc = frappe.get_doc("User", user)

	# Check if user is enabled
	if not user_doc.enabled:
		frappe.throw(_("Your account has been disabled"), frappe.AuthenticationError)

	# Generate API secret (regenerated each login for security)
	api_secret = frappe.generate_hash(length=15)

	# Generate API key if not exists
	if not user_doc.api_key:
		user_doc.api_key = frappe.generate_hash(length=15)

	# Update API secret
	user_doc.api_secret = api_secret
	user_doc.flags.ignore_permissions = True
	user_doc.save()
	frappe.db.commit()

	# Get user roles
	roles = frappe.get_roles(user)

	return {
		"message": "Login successful",
		"api_key": user_doc.api_key,
		"api_secret": api_secret,
		"user": {
			"name": user_doc.name,
			"email": user_doc.email,
			"full_name": user_doc.full_name,
			"username": user_doc.username,
			"user_image": user_doc.user_image,
			"is_admin": "Moderator" in roles,
			"is_student": "LMS Student" in roles,
			"roles": roles,
		},
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def api_sign_up(email, full_name, password, user_category="Student"):
	"""
	API signup endpoint - creates user with password and returns API tokens.
	User can immediately use the API after signup without email verification.

	Args:
		email: User email address
		full_name: User's full name
		password: User password (min 8 characters recommended)
		user_category: User category (default: "Student")

	Returns:
		dict: Contains api_key, api_secret, and user info on success

	Usage:
		POST /api/method/lms.lms.api.api_sign_up
		Body: {
			"email": "newuser@example.com",
			"full_name": "John Doe",
			"password": "securepassword123"
		}

		Response:
		{
			"message": "Signup successful",
			"api_key": "xxx",
			"api_secret": "yyy",
			"user": {...}
		}

		Then use token for authenticated requests:
		Authorization: token <api_key>:<api_secret>
	"""
	from frappe.utils import escape_html
	from frappe.website.utils import is_signup_disabled

	# Check if signup is disabled
	if is_signup_disabled():
		frappe.throw(_("Sign Up is disabled"), _("Not Allowed"))

	# Validate required fields
	if not email:
		frappe.throw(_("Email is required"))
	if not full_name:
		frappe.throw(_("Full name is required"))
	if not password:
		frappe.throw(_("Password is required"))

	# Validate email format
	if not frappe.utils.validate_email_address(email):
		frappe.throw(_("Please enter a valid email address"))

	# Validate password length
	if len(password) < 6:
		frappe.throw(_("Password must be at least 6 characters long"))

	# Check if user already exists
	existing_user = frappe.db.get("User", {"email": email})
	if existing_user:
		if existing_user.enabled:
			frappe.throw(_("User with this email already exists. Please login instead."))
		else:
			frappe.throw(_("This account exists but is disabled. Please contact support."))

	# Rate limiting - prevent mass signups
	if frappe.db.get_creation_count("User", 60) > 300:
		frappe.throw(_("Too many signups recently. Please try again in an hour."))

	# Generate API credentials
	api_key = frappe.generate_hash(length=15)
	api_secret = frappe.generate_hash(length=15)

	# Create user
	user = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": escape_html(full_name),
		"user_category": user_category,
		"enabled": 1,
		"new_password": password,
		"user_type": "Website User",
		"api_key": api_key,
		"api_secret": api_secret,
	})
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = True
	user.insert()

	# Add default roles
	default_role = frappe.db.get_single_value("Portal Settings", "default_role")
	if default_role:
		user.add_roles(default_role)
	user.add_roles("LMS Student")

	# Set country from IP
	from lms.lms.user import set_country_from_ip
	set_country_from_ip(None, user.name)

	frappe.db.commit()

	# Get user roles
	roles = frappe.get_roles(user.name)

	return {
		"message": "Signup successful",
		"api_key": api_key,
		"api_secret": api_secret,
		"user": {
			"name": user.name,
			"email": user.email,
			"full_name": user.full_name,
			"username": user.username,
			"user_image": user.user_image,
			"is_admin": False,
			"is_student": True,
			"roles": roles,
		},
	}


@frappe.whitelist(allow_guest=True)
def get_translations():
	if frappe.session.user != "Guest":
		language = frappe.db.get_value("User", frappe.session.user, "language")
	else:
		language = frappe.db.get_single_value("System Settings", "language")
	return get_all_translations(language)


@frappe.whitelist()
def validate_billing_access(billing_type, name):
	doctype = "LMS Batch" if billing_type == "batch" else "LMS Course"
	access, message = verify_billing_access(doctype, name, billing_type)

	address = frappe.db.get_value(
		"Address",
		{"email_id": frappe.session.user},
		[
			"name",
			"address_title as billing_name",
			"address_line1",
			"address_line2",
			"city",
			"state",
			"country",
			"pincode",
			"phone",
		],
		as_dict=1,
	)

	return {"access": access, "message": message, "address": address}


def verify_billing_access(doctype, name, billing_type):
	access = True
	message = ""

	if frappe.session.user == "Guest":
		access = False
		message = _("Please login to continue with payment.")

	if access and billing_type not in ["course", "batch", "certificate"]:
		access = False
		message = _("Module is incorrect.")

	if access and not frappe.db.exists(doctype, name):
		access = False
		message = _("Module Name is incorrect or does not exist.")

	if access and billing_type == "course":
		membership = frappe.db.exists("LMS Enrollment", {"member": frappe.session.user, "course": name})
		if membership:
			access = False
			message = _("You are already enrolled for this course.")

	elif access and billing_type == "batch":
		# Check for active enrollment only (not expired or manually removed)
		membership = frappe.db.exists("LMS Batch Enrollment", {
			"member": frappe.session.user,
			"batch": name,
			"status": ["in", ["Active", "Extended"]]
		})
		if membership:
			access = False
			message = _("You are already enrolled for this batch.")

		seat_count = frappe.get_cached_value("LMS Batch", name, "seat_count")
		# Count only active enrollments for seat availability
		number_of_students = frappe.db.count("LMS Batch Enrollment", {
			"batch": name,
			"status": ["in", ["Active", "Extended"]]
		})
		if seat_count <= number_of_students:
			access = False
			message = _("Batch is sold out.")

		start_date = frappe.get_cached_value("LMS Batch", name, "start_date")
		if start_date and date_diff(start_date, now()) < 0:
			access = False
			message = _("Batch has already started.")

	elif access and billing_type == "certificate":
		purchased_certificate = frappe.db.exists(
			"LMS Enrollment",
			{
				"course": name,
				"member": frappe.session.user,
				"purchased_certificate": 1,
			},
		)
		if purchased_certificate:
			access = False
			message = _("You have already purchased the certificate for this course.")

	return access, message


@frappe.whitelist(allow_guest=True)
def get_job_details(job):
	return frappe.db.get_value(
		"Job Opportunity",
		job,
		[
			"job_title",
			"location",
			"country",
			"type",
			"work_mode",
			"company_name",
			"company_logo",
			"company_website",
			"name",
			"creation",
			"description",
			"owner",
		],
		as_dict=1,
	)


@frappe.whitelist(allow_guest=True)
def get_job_opportunities(filters=None, orFilters=None):
	if not filters:
		filters = {}

	jobs = frappe.get_all(
		"Job Opportunity",
		filters=filters,
		or_filters=orFilters,
		fields=[
			"job_title",
			"location",
			"country",
			"type",
			"work_mode",
			"company_name",
			"company_logo",
			"name",
			"creation",
			"description",
		],
		order_by="creation desc",
	)

	for job in jobs:
		job.description = frappe.utils.strip_html_tags(job.description)
		job.applicants = frappe.db.count("LMS Job Application", {"job": job.name})
	return jobs


@frappe.whitelist(allow_guest=True)
def get_chart_details():
	details = frappe._dict()
	details.enrollments = frappe.db.count("LMS Enrollment")
	details.courses = frappe.db.count(
		"LMS Course",
		{
			"published": 1,
			"upcoming": 0,
		},
	)
	details.users = frappe.db.count("User", {"enabled": 1, "name": ["not in", ("Administrator", "Guest")]})
	details.completions = frappe.db.count("LMS Enrollment", {"progress": ["like", "%100%"]})
	details.certifications = frappe.db.count("LMS Certificate", {"published": 1})
	return details


@frappe.whitelist()
def get_file_info(file_url):
	"""Get file info for the given file URL."""
	file_info = frappe.db.get_value(
		"File", {"file_url": file_url}, ["file_name", "file_size", "file_url"], as_dict=1
	)
	return file_info


@frappe.whitelist(allow_guest=True)
def get_branding():
	"""Get branding details."""
	website_settings = frappe.get_single("Website Settings")
	image_fields = ["banner_image", "footer_logo", "favicon"]

	for field in image_fields:
		if website_settings.get(field):
			file_info = get_file_info(website_settings.get(field))
			website_settings.update({field: json.loads(json.dumps(file_info))})
		else:
			website_settings.update({field: None})

	return website_settings


@frappe.whitelist()
def get_unsplash_photos(keyword=None):
	from lms.unsplash import get_by_keyword, get_list

	if keyword:
		return get_by_keyword(keyword)

	return frappe.cache().get_value("unsplash_photos", generator=get_list)


@frappe.whitelist()
def get_evaluator_details(evaluator):
	frappe.only_for("Batch Evaluator")

	if not frappe.db.exists("Google Calendar", {"user": evaluator}):
		calendar = frappe.new_doc("Google Calendar")
		calendar.update({"user": evaluator, "calendar_name": evaluator})
		calendar.insert()
	else:
		calendar = frappe.db.get_value(
			"Google Calendar", {"user": evaluator}, ["name", "authorization_code"], as_dict=1
		)

	if frappe.db.exists("Course Evaluator", {"evaluator": evaluator}):
		doc = frappe.get_doc("Course Evaluator", evaluator)
	else:
		doc = frappe.new_doc("Course Evaluator")
		doc.evaluator = evaluator
		doc.insert()

	return {
		"slots": doc.as_dict(),
		"calendar": calendar.name,
		"is_authorised": calendar.authorization_code,
	}


@frappe.whitelist(allow_guest=True)
def get_certified_participants(filters=None, start=0, page_length=100):
	filters, or_filters, open_to_opportunities, hiring = update_certification_filters(filters)

	participants = frappe.db.get_all(
		"LMS Certificate",
		filters=filters,
		or_filters=or_filters,
		fields=["member", "issue_date", "batch_name", "course", "name"],
		group_by="member",
		order_by="issue_date desc",
		start=start,
		page_length=page_length,
	)

	for participant in participants:
		details = get_certified_participant_details(participant.member)
		participant.update(details)

	participants = filter_by_open_to_criteria(participants, open_to_opportunities, hiring)

	return participants


def update_certification_filters(filters):
	open_to_opportunities = False
	hiring = False
	or_filters = {}
	if not filters:
		filters = {}
	filters.update({"published": 1})

	category = filters.get("category")
	if category:
		del filters["category"]
		or_filters["course_title"] = ["like", f"%{category}%"]
		or_filters["batch_title"] = ["like", f"%{category}%"]

	if filters.get("open_to_opportunities"):
		del filters["open_to_opportunities"]
		open_to_opportunities = True

	if filters.get("hiring"):
		del filters["hiring"]
		hiring = True

	return filters, or_filters, open_to_opportunities, hiring


def get_certified_participant_details(member):
	count = frappe.db.count("LMS Certificate", {"member": member})
	details = frappe.db.get_value(
		"User",
		member,
		["full_name", "user_image", "username", "country", "headline", "open_to"],
		as_dict=1,
	)
	details["certificate_count"] = count
	return details


def filter_by_open_to_criteria(participants, open_to_opportunities, hiring):
	if not open_to_opportunities and not hiring:
		return participants

	if open_to_opportunities:
		participants = [participant for participant in participants if participant.open_to == "Opportunities"]

	if hiring:
		participants = [participant for participant in participants if participant.open_to == "Hiring"]

	return participants


@frappe.whitelist(allow_guest=True)
def get_count_of_certified_members(filters=None):
	Certificate = DocType("LMS Certificate")

	query = (
		frappe.qb.from_(Certificate).select(Certificate.member).distinct().where(Certificate.published == 1)
	)

	if filters:
		for field, value in filters.items():
			if field == "category":
				query = query.where(
					Certificate.course_title.like(f"%{value}%") | Certificate.batch_title.like(f"%{value}%")
				)
			elif field == "member_name":
				query = query.where(Certificate.member_name.like(value[1]))

	result = query.run(as_dict=True)
	return len(result) or 0


@frappe.whitelist(allow_guest=True)
def get_certification_categories():
	categories = []
	seen = set()
	docs = frappe.get_all(
		"LMS Certificate",
		filters={
			"published": 1,
		},
		fields=["course_title", "batch_title"],
	)

	for doc in docs:
		category = doc.course_title if doc.course_title else doc.batch_title
		if not category or category in seen:
			continue

		seen.add(category)
		categories.append({"label": category, "value": category})
	return categories


@frappe.whitelist()
def get_assigned_badges(member):
	assigned_badges = frappe.get_all(
		"LMS Badge Assignment",
		{"member": member},
		["badge"],
		as_dict=1,
	)

	for badge in assigned_badges:
		badge.update(frappe.db.get_value("LMS Badge", badge.badge, ["name", "title", "image"]))
	return assigned_badges


@frappe.whitelist()
def get_all_users():
	frappe.only_for(["Moderator", "Course Creator", "Batch Evaluator"])
	users = frappe.get_all(
		"User",
		{
			"enabled": 1,
		},
		["name", "full_name", "user_image"],
	)

	return {user.name: user for user in users}


@frappe.whitelist()
def mark_as_read(name):
	doc = frappe.get_doc("Notification Log", name)
	doc.read = 1
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def mark_all_as_read():
	notifications = frappe.get_all(
		"Notification Log", {"for_user": frappe.session.user, "read": 0}, pluck="name"
	)

	for notification in notifications:
		mark_as_read(notification)


@frappe.whitelist(allow_guest=True)
def get_sidebar_settings():
	lms_settings = frappe.get_single("LMS Settings")
	sidebar_items = frappe._dict()

	items = [
		"courses",
		"batches",
		"certifications",
		"jobs",
		"statistics",
		"notifications",
		"programming_exercises",
	]
	for item in items:
		sidebar_items[item] = lms_settings.get(item)

	if len(lms_settings.sidebar_items):
		web_pages = frappe.get_all(
			"LMS Sidebar Item",
			{"parenttype": "LMS Settings", "parentfield": "sidebar_items"},
			["web_page", "route", "title as label", "icon", "name"],
		)
		for page in web_pages:
			page.to = page.route

		sidebar_items.web_pages = web_pages

	return sidebar_items


@frappe.whitelist()
def update_sidebar_item(webpage, icon):
	filters = {
		"web_page": webpage,
		"parenttype": "LMS Settings",
		"parentfield": "sidebar_items",
		"parent": "LMS Settings",
	}

	if frappe.db.exists("LMS Sidebar Item", filters):
		frappe.db.set_value("LMS Sidebar Item", filters, "icon", icon)
	else:
		doc = frappe.new_doc("LMS Sidebar Item")
		doc.update(filters)
		doc.icon = icon
		doc.insert()


@frappe.whitelist()
def delete_sidebar_item(webpage):
	return frappe.db.delete(
		"LMS Sidebar Item",
		{
			"web_page": webpage,
			"parenttype": "LMS Settings",
			"parentfield": "sidebar_items",
			"parent": "LMS Settings",
		},
	)


@frappe.whitelist()
def delete_lesson(lesson, chapter):
	# Delete Reference
	chapter = frappe.get_doc("Course Chapter", chapter)
	chapter.lessons = [row for row in chapter.lessons if row.lesson != lesson]
	chapter.save()

	# Delete progress
	frappe.db.delete("LMS Course Progress", {"lesson": lesson})

	# Delete Lesson
	frappe.db.delete("Course Lesson", lesson)


@frappe.whitelist()
def update_lesson_index(lesson, sourceChapter, targetChapter, idx):
	hasMoved = sourceChapter == targetChapter

	update_source_chapter(lesson, sourceChapter, idx, hasMoved)
	if not hasMoved:
		update_target_chapter(lesson, targetChapter, idx)


def update_source_chapter(lesson, chapter, idx, hasMoved=False):
	lessons = frappe.get_all(
		"Lesson Reference",
		{
			"parent": chapter,
		},
		pluck="lesson",
		order_by="idx",
	)

	lessons.remove(lesson)
	if not hasMoved:
		frappe.db.delete("Lesson Reference", {"parent": chapter, "lesson": lesson})
	else:
		lessons.insert(idx, lesson)

	update_index(lessons, chapter)


def update_target_chapter(lesson, chapter, idx):
	lessons = frappe.get_all(
		"Lesson Reference",
		{
			"parent": chapter,
		},
		pluck="lesson",
		order_by="idx",
	)

	lessons.insert(idx, lesson)
	new_lesson_reference = frappe.new_doc("Lesson Reference")
	new_lesson_reference.update(
		{
			"lesson": lesson,
			"parent": chapter,
			"parenttype": "Course Chapter",
			"parentfield": "lessons",
		}
	)
	new_lesson_reference.insert()
	update_index(lessons, chapter)


def update_index(lessons, chapter):
	for row in lessons:
		frappe.db.set_value(
			"Lesson Reference", {"lesson": row, "parent": chapter}, "idx", lessons.index(row) + 1
		)


@frappe.whitelist()
def update_chapter_index(chapter, course, idx):
	"""Update the index of a chapter within a course"""
	chapters = frappe.get_all(
		"Chapter Reference",
		{"parent": course},
		pluck="chapter",
		order_by="idx",
	)

	if chapter in chapters:
		chapters.remove(chapter)

	chapters.insert(idx, chapter)

	for i, chapter_name in enumerate(chapters):
		frappe.db.set_value("Chapter Reference", {"chapter": chapter_name, "parent": course}, "idx", i + 1)


@frappe.whitelist(allow_guest=True)
def get_categories(doctype, filters):
	categoryOptions = []

	categories = frappe.get_all(
		doctype,
		filters,
		pluck="category",
	)
	categories = list(set(categories))

	for category in categories:
		if category:
			categoryOptions.append({"label": category, "value": category})

	return categoryOptions


@frappe.whitelist()
def get_members(start=0, search=""):
	filters = {"enabled": 1, "name": ["not in", ["Administrator", "Guest"]]}
	or_filters = {}

	if search:
		or_filters["full_name"] = ["like", f"%{search}%"]
		or_filters["email"] = ["like", f"%{search}%"]

	members = frappe.get_all(
		"User",
		filters=filters,
		fields=["name", "full_name", "user_image", "username", "last_active"],
		or_filters=or_filters,
		page_length=20,
		start=start,
	)

	for member in members:
		roles = frappe.get_all(
			"Has Role",
			{
				"parent": member.name,
				"parenttype": "User",
			},
			pluck="role",
		)
		if "Moderator" in roles:
			member.role = "Moderator"
		elif "Course Creator" in roles:
			member.role = "Course Creator"
		elif "Batch Evaluator" in roles:
			member.role = "Batch Evaluator"
		elif "LMS Student" in roles:
			member.role = "LMS Student"

	return members


def check_app_permission():
	"""Check if the user has permission to access the app."""
	if frappe.session.user == "Administrator":
		return True

	roles = frappe.get_roles()
	lms_roles = ["Moderator", "Course Creator", "Batch Evaluator", "LMS Student"]
	if any(role in roles for role in lms_roles):
		return True

	return False


@frappe.whitelist()
def save_evaluation_details(
	member,
	course,
	batch_name,
	evaluator,
	date,
	start_time,
	end_time,
	status,
	rating,
	summary,
):
	"""
	Save evaluation details for a member against a course.
	"""
	evaluation = frappe.db.exists("LMS Certificate Evaluation", {"member": member, "course": course})

	details = {
		"date": date,
		"start_time": start_time,
		"end_time": end_time,
		"status": status,
		"rating": rating / 5,
		"summary": summary,
		"batch_name": batch_name,
	}

	if evaluation:
		frappe.db.set_value("LMS Certificate Evaluation", evaluation, details)
		return evaluation
	else:
		doc = frappe.new_doc("LMS Certificate Evaluation")
		details.update(
			{
				"member": member,
				"course": course,
				"evaluator": evaluator,
			}
		)
		doc.update(details)
		doc.insert()
		return doc.name


@frappe.whitelist()
def save_certificate_details(
	member,
	course,
	batch_name,
	evaluator,
	issue_date,
	expiry_date,
	template,
	published=True,
):
	"""
	Save certificate details for a member against a course.
	"""
	certificate = frappe.db.exists("LMS Certificate", {"member": member, "course": course})

	details = {
		"published": published,
		"issue_date": issue_date,
		"expiry_date": expiry_date,
		"template": template,
		"batch_name": batch_name,
	}

	if certificate:
		frappe.db.set_value("LMS Certificate", certificate, details)
		return certificate
	else:
		doc = frappe.new_doc("LMS Certificate")
		details.update(
			{
				"member": member,
				"course": course,
				"evaluator": evaluator,
			}
		)
		doc.update(details)
		doc.insert()
		return doc.name


@frappe.whitelist()
def delete_documents(doctype, documents):
	frappe.only_for(["Moderator", "Course Creator"])
	for doc in documents:
		frappe.delete_doc(doctype, doc)


@frappe.whitelist(allow_guest=True)
def get_count(doctype, filters):
	return frappe.db.count(
		doctype,
		filters=filters,
	)


@frappe.whitelist()
def get_payment_gateway_details(payment_gateway):
	gateway = frappe.get_doc("Payment Gateway", payment_gateway)

	if gateway.gateway_controller is None:
		try:
			data = frappe.get_doc(f"{payment_gateway} Settings").as_dict()
			meta = frappe.get_meta(f"{payment_gateway} Settings").fields
			doctype = f"{payment_gateway} Settings"
			docname = f"{payment_gateway} Settings"
		except Exception:
			frappe.throw(_("{0} Settings not found").format(payment_gateway))
	else:
		try:
			data = frappe.get_doc(gateway.gateway_settings, gateway.gateway_controller).as_dict()
			meta = frappe.get_meta(gateway.gateway_settings).fields
			doctype = gateway.gateway_settings
			docname = gateway.gateway_controller
		except Exception:
			frappe.throw(_("{0} Settings not found").format(payment_gateway))

	gateway_fields = get_transformed_fields(meta, data)

	return {
		"fields": gateway_fields,
		"data": data,
		"doctype": doctype,
		"docname": docname,
	}


def get_transformed_fields(meta, data=None):
	transformed_fields = []
	for row in meta:
		if row.fieldtype not in ["Column Break", "Section Break"]:
			if row.fieldtype in ["Attach", "Attach Image"]:
				fieldtype = "Upload"
				if data and data.get(row.fieldname):
					data[row.fieldname] = get_file_info(data.get(row.fieldname))
			elif row.fieldtype == "Check":
				fieldtype = "checkbox"
			else:
				fieldtype = row.fieldtype

			transformed_fields.append(
				{
					"label": row.label,
					"name": row.fieldname,
					"type": fieldtype,
				}
			)

	return transformed_fields


@frappe.whitelist()
def get_new_gateway_fields(doctype):
	try:
		meta = frappe.get_meta(doctype).fields
	except Exception:
		frappe.throw(_("{0} not found").format(doctype))

	transformed_fields = get_transformed_fields(meta)

	return transformed_fields


def update_course_statistics():
	courses = frappe.get_all("LMS Course", fields=["name"])

	for course in courses:
		lessons = get_lesson_count(course.name)

		enrollments = frappe.db.count("LMS Enrollment", {"course": course.name, "member_type": "Student"})

		avg_rating = get_average_rating(course.name) or 0
		avg_rating = flt(avg_rating, frappe.get_system_settings("float_precision") or 3)

		frappe.db.set_value(
			"LMS Course",
			course.name,
			{"lessons": lessons, "enrollments": enrollments, "rating": avg_rating},
		)


@frappe.whitelist()
def get_announcements(batch):
	communications = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "LMS Batch",
			"reference_name": batch,
		},
		fields=[
			"subject",
			"content",
			"recipients",
			"cc",
			"communication_date",
			"sender",
			"sender_full_name",
		],
		order_by="communication_date desc",
	)

	for communication in communications:
		communication.image = frappe.get_cached_value("User", communication.sender, "user_image")

	return communications


@frappe.whitelist()
def delete_course(course):
	chapters = frappe.get_all("Course Chapter", {"course": course}, pluck="name")

	chapter_references = frappe.get_all("Chapter Reference", {"parent": course}, pluck="name")

	for chapter in chapters:
		lessons = frappe.get_all("Course Lesson", {"chapter": chapter}, pluck="name")

		lesson_references = frappe.get_all("Lesson Reference", {"parent": chapter}, pluck="name")

		for lesson in lesson_references:
			frappe.delete_doc("Lesson Reference", lesson)

		for lesson in lessons:
			topics = frappe.get_all(
				"Discussion Topic",
				{"reference_doctype": "Course Lesson", "reference_docname": lesson},
				pluck="name",
			)

			for topic in topics:
				frappe.db.delete("Discussion Reply", {"topic": topic})

				frappe.db.delete("Discussion Topic", topic)

			frappe.delete_doc("Course Lesson", lesson)

	for chapter in chapter_references:
		frappe.delete_doc("Chapter Reference", chapter)

	for chapter in chapters:
		frappe.delete_doc("Course Chapter", chapter)

	frappe.db.delete("LMS Course Progress", {"course": course})
	frappe.db.delete("LMS Quiz", {"course": course})
	frappe.db.delete("LMS Quiz Submission", {"course": course})
	frappe.db.delete("LMS Enrollment", {"course": course})
	frappe.delete_doc("LMS Course", course)


@frappe.whitelist()
def delete_batch(batch):
	frappe.db.delete("LMS Batch Enrollment", {"batch": batch})
	frappe.db.delete("Batch Course", {"parent": batch, "parenttype": "LMS Batch"})
	frappe.db.delete("LMS Assessment", {"parent": batch, "parenttype": "LMS Batch"})
	frappe.db.delete("LMS Batch Timetable", {"parent": batch, "parenttype": "LMS Batch"})
	frappe.db.delete("LMS Batch Feedback", {"batch": batch})
	delete_batch_discussions(batch)
	frappe.db.delete("LMS Batch", batch)


def delete_batch_discussions(batch):
	topics = frappe.get_all(
		"Discussion Topic",
		{"reference_doctype": "LMS Batch", "reference_docname": batch},
		pluck="name",
	)

	for topic in topics:
		frappe.db.delete("Discussion Reply", {"topic": topic})
		frappe.db.delete("Discussion Topic", topic)


def give_discussions_permission():
	doctypes = ["Discussion Topic", "Discussion Reply"]
	roles = ["LMS Student", "Course Creator", "Moderator", "Batch Evaluator"]
	for doctype in doctypes:
		for role in roles:
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role}):
				frappe.get_doc(
					{
						"doctype": "Custom DocPerm",
						"parent": doctype,
						"role": role,
						"read": 1,
						"write": 1,
						"create": 1,
						"delete": 1,
						"if_owner": 0 if role == "Moderator" else 1,
					}
				).save(ignore_permissions=True)


@frappe.whitelist()
def upsert_chapter(title, course, is_scorm_package, scorm_package, name=None):
	values = frappe._dict({"title": title, "course": course, "is_scorm_package": is_scorm_package})

	if is_scorm_package:
		scorm_package = frappe._dict(scorm_package)
		extract_path = extract_package(course, title, scorm_package)

		values.update(
			{
				"scorm_package": scorm_package.name,
				"scorm_package_path": extract_path.split("public")[1],
				"manifest_file": get_manifest_file(extract_path).split("public")[1],
				"launch_file": get_launch_file(extract_path).split("public")[1],
			}
		)

	if name:
		chapter = frappe.get_doc("Course Chapter", name)
	else:
		chapter = frappe.new_doc("Course Chapter")

	chapter.update(values)
	chapter.save()

	if is_scorm_package and not len(chapter.lessons):
		add_lesson(title, chapter.name, course, 1)

	return chapter


def extract_package(course, title, scorm_package):
	package = frappe.get_doc("File", scorm_package.name)
	zip_path = package.get_full_path()
	# check_for_malicious_code(zip_path)
	extract_path = frappe.get_site_path("public", "scorm", course, title)
	zipfile.ZipFile(zip_path).extractall(extract_path)
	return extract_path


def check_for_malicious_code(zip_path):
	suspicious_patterns = [
		# Unsafe inline JavaScript
		r'on(click|load|mouseover|error|submit|focus|blur|change|keyup|keydown|keypress|resize)=".*?"',  # Inline event handlers (e.g., onerror, onclick)
		r'<script.*?src=["\']http',  # External script tags
		r"eval\(",  # Usage of eval()
		r"Function\(",  # Usage of Function constructor
		r"(btoa|atob)\(",  # Base64 encoding/decoding
		# Dangerous XML patterns
		r"<!ENTITY",  # XXE-related
		r"<\?xml-stylesheet .*?>",  # External stylesheets in XML
	]

	with zipfile.ZipFile(zip_path, "r") as zf:
		for file_name in zf.namelist():
			if file_name.endswith((".html", ".js", ".xml")):
				with zf.open(file_name) as file:
					content = file.read().decode("utf-8", errors="ignore")
					for pattern in suspicious_patterns:
						if re.search(pattern, content):
							frappe.throw(_("Suspicious pattern found in {0}: {1}").format(file_name, pattern))


def get_manifest_file(extract_path):
	manifest_file = None
	for root, _dirs, files in os.walk(extract_path):
		for file in files:
			if file == "imsmanifest.xml":
				manifest_file = os.path.join(root, file)
				break
		if manifest_file:
			break
	return manifest_file


def get_launch_file(extract_path):
	launch_file = None
	manifest_file = get_manifest_file(extract_path)

	if manifest_file:
		with open(manifest_file) as file:
			data = file.read()
			dom = parseString(data)
			resource = dom.getElementsByTagName("resource")
			for res in resource:
				if (
					res.getAttribute("adlcp:scormtype") == "sco"
					or res.getAttribute("adlcp:scormType") == "sco"
				):
					launch_file = res.getAttribute("href")
					break

		if launch_file:
			launch_file = os.path.join(os.path.dirname(manifest_file), launch_file)

	return launch_file


def add_lesson(title, chapter, course, idx):
	lesson = frappe.new_doc("Course Lesson")
	lesson.update(
		{
			"title": title,
			"chapter": chapter,
			"course": course,
		}
	)
	lesson.insert()

	lesson_reference = frappe.new_doc("Lesson Reference")
	lesson_reference.update(
		{
			"lesson": lesson.name,
			"idx": idx,
			"parent": chapter,
			"parenttype": "Course Chapter",
			"parentfield": "lessons",
		}
	)
	lesson_reference.insert()


@frappe.whitelist()
def delete_chapter(chapter):
	chapterInfo = frappe.db.get_value(
		"Course Chapter", chapter, ["is_scorm_package", "scorm_package_path"], as_dict=True
	)

	if chapterInfo.is_scorm_package:
		delete_scorm_package(chapterInfo.scorm_package_path)

	frappe.db.delete("Chapter Reference", {"chapter": chapter})
	frappe.db.delete("Lesson Reference", {"parent": chapter})
	frappe.db.delete("Course Lesson", {"chapter": chapter})
	frappe.db.delete("Course Chapter", chapter)


def delete_scorm_package(scorm_package_path):
	scorm_package_path = frappe.get_site_path("public", scorm_package_path[1:])
	if os.path.exists(scorm_package_path):
		shutil.rmtree(scorm_package_path)


@frappe.whitelist()
def mark_lesson_progress(course, chapter_number, lesson_number):
	chapter_name = frappe.get_value("Chapter Reference", {"parent": course, "idx": chapter_number}, "chapter")
	lesson_name = frappe.get_value(
		"Lesson Reference", {"parent": chapter_name, "idx": lesson_number}, "lesson"
	)
	save_progress(lesson_name, course)


@frappe.whitelist()
def get_heatmap_data(member=None, base_days=200):
	if not member:
		member = frappe.session.user

	base_date, start_date, number_of_days, days = calculate_date_ranges(base_days)
	date_count = initialize_date_count(days)

	lesson_completions, quiz_submissions, assignment_submissions = fetch_activity_data(member, start_date)
	count_dates(lesson_completions, date_count)
	count_dates(quiz_submissions, date_count)
	count_dates(assignment_submissions, date_count)

	heatmap_data, labels, total_activities, weeks = prepare_heatmap_data(
		start_date, number_of_days, date_count
	)

	return {
		"heatmap_data": heatmap_data,
		"labels": labels,
		"total_activities": total_activities,
		"weeks": weeks,
	}


def calculate_date_ranges(base_days):
	today = format_date(now(), "YYYY-MM-dd")
	day_today = get_datetime(today).strftime("%w")
	padding_end = 6 - cint(day_today)

	base_date = add_days(today, -base_days)
	day_of_base_date = cint(get_datetime(base_date).strftime("%w"))
	start_date = add_days(base_date, -day_of_base_date)
	number_of_days = base_days + day_of_base_date + padding_end
	days = [add_days(start_date, i) for i in range(number_of_days + 1)]

	return base_date, start_date, number_of_days, days


def initialize_date_count(days):
	return {format_date(day, "YYYY-MM-dd"): 0 for day in days}


def fetch_activity_data(member, start_date):
	lesson_completions = frappe.get_all(
		"LMS Course Progress",
		fields=["creation"],
		filters={"member": member, "creation": [">=", start_date], "status": "Complete"},
	)

	quiz_submissions = frappe.get_all(
		"LMS Quiz Submission",
		fields=["creation"],
		filters={"member": member, "creation": [">=", start_date]},
	)

	assignment_submissions = frappe.get_all(
		"LMS Assignment Submission",
		fields=["creation"],
		filters={"member": member, "creation": [">=", start_date]},
	)

	return lesson_completions, quiz_submissions, assignment_submissions


def count_dates(data, date_count):
	for entry in data:
		date = format_date(entry.creation, "YYYY-MM-dd")
		if date in date_count:
			date_count[date] += 1


def prepare_heatmap_data(start_date, number_of_days, date_count):
	days_of_week = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
	heatmap_data = {day: [] for day in days_of_week}
	week_count = -(number_of_days // -7)
	labels = [None] * week_count
	last_seen_month = None
	sorted_dates = sorted(date_count.keys())

	for date in sorted_dates:
		activity_count = date_count[date]
		day_of_week = get_datetime(date).strftime("%a")
		current_month = get_datetime(date).strftime("%b")
		column_index = get_week_difference(start_date, date)

		if 0 <= column_index < week_count:
			heatmap_data[day_of_week].append(
				{
					"date": date,
					"count": activity_count,
					"label": f"{activity_count} activities on {format_date(date, 'dd MMM')}",
				}
			)

			if last_seen_month != current_month:
				labels[column_index] = current_month
				last_seen_month = current_month

	for index, label in enumerate(labels):
		if not label:
			labels[index] = ""

	formatted_heatmap_data = [{"name": day, "data": heatmap_data[day]} for day in days_of_week]

	total_activities = sum(date_count.values())
	return formatted_heatmap_data, labels, total_activities, week_count


def get_week_difference(start_date, current_date):
	diff_in_days = date_diff(current_date, start_date)
	return diff_in_days // 7


@frappe.whitelist()
def get_notifications(filters):
	notifications = frappe.get_all(
		"Notification Log",
		filters,
		["subject", "from_user", "link", "read", "name"],
		order_by="creation desc",
	)

	for notification in notifications:
		from_user_details = frappe.db.get_value(
			"User", notification.from_user, ["full_name", "user_image"], as_dict=1
		)
		notification.update(from_user_details)

	return notifications


@frappe.whitelist(allow_guest=True)
def get_lms_settings():
	allowed_fields = [
		"allow_guest_access",
		"prevent_skipping_videos",
		"contact_us_email",
		"contact_us_url",
		"livecode_url",
		"disable_pwa",
	]

	settings = frappe._dict()
	for field in allowed_fields:
		settings[field] = frappe.get_cached_value("LMS Settings", None, field)

	return settings


@frappe.whitelist()
def cancel_evaluation(evaluation):
	evaluation = frappe._dict(evaluation)

	if evaluation.member != frappe.session.user:
		return

	frappe.db.set_value("LMS Certificate Request", evaluation.name, "status", "Cancelled")
	events = frappe.get_all(
		"Event Participants",
		{
			"email": evaluation.member,
		},
		["parent", "name"],
	)

	for event in events:
		info = frappe.db.get_value("Event", event.parent, ["starts_on", "subject"], as_dict=1)
		date = str(info.starts_on).split(" ")[0]

		if date == str(evaluation.date.format("YYYY-MM-DD")) and evaluation.member_name in info.subject:
			communication = frappe.db.get_value(
				"Communication",
				{"reference_doctype": "Event", "reference_name": event.parent},
				"name",
			)
			if communication:
				frappe.delete_doc("Communication", communication, ignore_permissions=True)

			frappe.delete_doc("Event Participants", event.name, ignore_permissions=True)
			frappe.delete_doc("Event", event.parent, ignore_permissions=True)


@frappe.whitelist()
def get_certification_details(course):
	membership = None
	filters = {"course": course, "member": frappe.session.user}

	if frappe.db.exists("LMS Enrollment", filters):
		membership = frappe.db.get_value(
			"LMS Enrollment",
			filters,
			["name", "purchased_certificate"],
			as_dict=1,
		)

	paid_certificate = frappe.db.get_value("LMS Course", course, "paid_certificate")
	certificate = frappe.db.get_value(
		"LMS Certificate",
		{"member": frappe.session.user, "course": course},
		["name", "template"],
		as_dict=1,
	)

	return {
		"membership": membership,
		"paid_certificate": paid_certificate,
		"certificate": certificate,
	}


@frappe.whitelist()
def save_role(user, role, value):
	"""
	Save a role for a user. Only Admin (Moderator) can manage roles.
	Supports the 4-role model: Admin, Course Creator, Teacher, Student
	"""
	frappe.only_for("Moderator")

	# Map UI role names to internal Frappe role names
	role_mapping = {
		"Admin": "Moderator",
		"Course Creator": "Course Creator",
		"Teacher": "Teacher",
		"Student": "LMS Student",
		# Legacy mappings for backward compatibility
		"Moderator": "Moderator",
		"LMS Student": "LMS Student",
	}

	internal_role = role_mapping.get(role, role)

	if cint(value):
		doc = frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": user,
				"role": internal_role,
				"parenttype": "User",
				"parentfield": "roles",
			}
		)
		doc.save(ignore_permissions=True)
	else:
		frappe.db.delete("Has Role", {"parent": user, "role": internal_role})
	frappe.clear_cache(user=user)
	return True


@frappe.whitelist()
def add_an_evaluator(email):
	frappe.only_for("Moderator")
	if not frappe.db.exists("User", email):
		user = frappe.new_doc("User")
		user.update(
			{
				"email": email,
				"first_name": email.split("@")[0].capitalize(),
				"enabled": 1,
			}
		)
		user.insert()
		user.add_roles("Batch Evaluator")

	evaluator = frappe.new_doc("Course Evaluator")
	evaluator.evaluator = email
	evaluator.insert()

	return evaluator


@frappe.whitelist()
def delete_evaluator(evaluator):
	frappe.only_for("Moderator")
	if not frappe.db.exists("Course Evaluator", evaluator):
		frappe.throw(_("Evaluator does not exist."))

	frappe.db.delete("Has Role", {"parent": evaluator, "role": "Batch Evaluator"})
	frappe.db.delete("Course Evaluator", evaluator)


@frappe.whitelist()
def get_instructors(txt=""):
	"""
	Get users who can be instructors for a batch.
	Returns users with Teacher, Batch Evaluator, or Course Creator roles.
	Format matches frappe.desk.search.search_link for compatibility with MultiSelect.
	"""
	txt = txt or ""

	# Get users with teacher-related roles
	users_with_roles = frappe.db.sql(
		"""
		SELECT DISTINCT u.name, u.full_name
		FROM `tabUser` u
		INNER JOIN `tabHas Role` hr ON hr.parent = u.name
		WHERE hr.role IN ('Teacher', 'Batch Evaluator', 'Course Creator')
		AND u.enabled = 1
		AND (u.name LIKE %s OR u.full_name LIKE %s)
		ORDER BY u.full_name
		LIMIT 20
		""",
		(f"%{txt}%", f"%{txt}%"),
		as_dict=True,
	)

	# Format to match search_link response
	results = []
	for user in users_with_roles:
		results.append({
			"value": user.name,
			"description": user.full_name or user.name,
		})

	return results


@frappe.whitelist()
def capture_user_persona(responses):
	frappe.only_for("System Manager")
	data = frappe.parse_json(responses)
	data = json.dumps(data)
	response = frappe.integrations.utils.make_post_request(
		"https://school.frappe.io/api/method/capture-persona",
		data={"response": data},
	)
	if response.get("message").get("name"):
		frappe.db.set_single_value("LMS Settings", "persona_captured", True)
	return response


@frappe.whitelist()
def get_meta_info(type, route):
	if frappe.db.exists("Website Meta Tag", {"parent": f"{type}/{route}"}):
		meta_tags = frappe.get_all(
			"Website Meta Tag",
			{
				"parent": f"{type}/{route}",
			},
			["name", "key", "value"],
		)

		return meta_tags

	return []


@frappe.whitelist()
def update_meta_info(meta_type, route, meta_tags):
	validate_meta_data_permissions(meta_type)
	validate_meta_tags(meta_tags)

	parent_name = f"{meta_type}/{route}"
	for tag in meta_tags:
		existing_tag = frappe.db.exists(
			"Website Meta Tag",
			{
				"parent": parent_name,
				"parenttype": "Website Route Meta",
				"parentfield": "meta_tags",
				"key": tag["key"],
			},
		)
		if existing_tag:
			if not tag.get("value"):
				frappe.db.delete("Website Meta Tag", existing_tag)
				continue
			frappe.db.set_value("Website Meta Tag", existing_tag, "value", tag["value"])
		elif tag.get("value"):
			tag_properties = {
				"parent": parent_name,
				"parenttype": "Website Route Meta",
				"parentfield": "meta_tags",
				"key": tag["key"],
				"value": tag["value"],
			}

			parent_exists = frappe.db.exists("Website Route Meta", parent_name)
			if not parent_exists:
				create_meta(parent_name, tag_properties)
			else:
				create_meta_tag(tag_properties)


def validate_meta_tags(meta_tags):
	if not isinstance(meta_tags, list):
		frappe.throw(_("Meta tags should be a list."))


def create_meta(parent_name, tag_properties):
	route_meta = frappe.new_doc("Website Route Meta")
	route_meta.update(
		{
			"__newname": parent_name,
		}
	)
	route_meta.append("meta_tags", tag_properties)
	route_meta.insert()


def create_meta_tag(tag_properties):
	new_tag = frappe.new_doc("Website Meta Tag")
	new_tag.update(tag_properties)
	new_tag.insert()


def validate_meta_data_permissions(meta_type):
	roles = frappe.get_roles()

	if meta_type == "courses":
		if not ("Course Creator" in roles or "Moderator" in roles):
			frappe.throw(_("You do not have permission to update meta tags."))

	elif meta_type == "batches":
		if not ("Batch Evaluator" in roles or "Moderator" in roles):
			frappe.throw(_("You do not have permission to update meta tags."))


@frappe.whitelist()
def create_programming_exercise_submission(exercise, submission, code, test_cases):
	if submission == "new":
		return make_new_exercise_submission(exercise, code, test_cases)
	else:
		update_exercise_submission(submission, code, test_cases)


def make_new_exercise_submission(exercise, code, test_cases):
	submission = frappe.new_doc("LMS Programming Exercise Submission")
	submission.exercise = exercise
	submission.member = frappe.session.user
	submission.code = code

	for test_case in test_cases:
		submission.append(
			"test_cases",
			{
				"input": test_case.get("input"),
				"output": test_case.get("output"),
				"expected_output": test_case.get("expected_output"),
				"status": test_case.get("status", test_case.get("status", "Failed")),
			},
		)

	submission.status = get_exercise_status(test_cases)
	submission.insert()
	return submission.name


def update_exercise_submission(submission, code, test_cases):
	update_test_cases(test_cases, submission)
	status = get_exercise_status(test_cases)
	frappe.db.set_value("LMS Programming Exercise Submission", submission, {"status": status, "code": code})


def get_exercise_status(test_cases):
	if not test_cases:
		return "Failed"

	if all(row.get("status", "Failed") == "Passed" for row in test_cases):
		return "Passed"
	else:
		return "Failed"


def update_test_cases(test_cases, submission):
	frappe.db.delete("LMS Test Case Submission", {"parent": submission})
	for row in test_cases:
		test_case = frappe.new_doc("LMS Test Case Submission")
		test_case.update(
			{
				"parent": submission,
				"parenttype": "LMS Programming Exercise Submission",
				"parentfield": "test_cases",
				"input": row.get("input"),
				"output": row.get("output"),
				"expected_output": row.get("expected_output"),
				"status": row.get("status", "Failed"),
			}
		)
		test_case.insert()


@frappe.whitelist()
def track_video_watch_duration(lesson, videos):
	"""
	Track the watch duration of videos in a lesson.
	"""
	# Check if user has access to this lesson's course
	course = frappe.db.get_value("Course Lesson", lesson, "course")
	if not course:
		return

	enrollment = frappe.db.get_value(
		"LMS Enrollment",
		{"course": course, "member": frappe.session.user},
		["name", "enrollment_from_batch"],
		as_dict=True
	)
	if not enrollment:
		return

	# If enrollment is from a batch, verify batch enrollment is still active
	if enrollment.enrollment_from_batch:
		batch_enrollment_active = frappe.db.exists(
			"LMS Batch Enrollment",
			{
				"member": frappe.session.user,
				"batch": enrollment.enrollment_from_batch,
				"status": ["in", ["Active", "Extended"]]
			}
		)
		if not batch_enrollment_active:
			return

	if not isinstance(videos, list):
		videos = json.loads(videos)

	for video in videos:
		filters = {
			"lesson": lesson,
			"source": video.get("source"),
			"member": frappe.session.user,
		}
		existing_record = frappe.db.get_value(
			"LMS Video Watch Duration", filters, ["name", "watch_time"], as_dict=True
		)
		if existing_record and flt(existing_record.watch_time) < flt(video.get("watch_time")):
			frappe.db.set_value(
				"LMS Video Watch Duration",
				filters,
				"watch_time",
				video.get("watch_time"),
			)
		elif not existing_record:
			track_new_watch_time(lesson, video)


def track_new_watch_time(lesson, video):
	doc = frappe.new_doc("LMS Video Watch Duration")
	doc.lesson = lesson
	doc.source = video.get("source")
	doc.watch_time = video.get("watch_time")
	doc.member = frappe.session.user
	doc.save()


@frappe.whitelist()
def get_course_progress_distribution(course):
	all_progress = frappe.get_all(
		"LMS Enrollment",
		{
			"course": course,
		},
		pluck="progress",
	)

	average_progress = get_average_course_progress(all_progress)
	progress_distribution = get_progress_distribution(all_progress)

	return {
		"average_progress": average_progress,
		"progress_distribution": progress_distribution,
	}


def get_average_course_progress(progress_list):
	if not progress_list:
		return 0
	average_progress = sum(progress_list) / len(progress_list)
	return flt(average_progress, frappe.get_system_settings("float_precision") or 3)


def get_progress_distribution(progressList):
	distribution = [
		{
			"category": "0-20%",
			"count": len([p for p in progressList if 0 <= p < 20]),
		},
		{
			"category": "20-40%",
			"count": len([p for p in progressList if 20 <= p < 40]),
		},
		{
			"category": "40-60%",
			"count": len([p for p in progressList if 40 <= p < 60]),
		},
		{
			"category": "60-80%",
			"count": len([p for p in progressList if 60 <= p < 80]),
		},
		{
			"category": "80-100%",
			"count": len([p for p in progressList if 80 <= p <= 100]),
		},
	]

	return distribution


@frappe.whitelist(allow_guest=True)
def get_pwa_manifest():
	title = frappe.db.get_single_value("Website Settings", "app_name") or "Frappe Learning"
	banner_image = frappe.db.get_single_value("Website Settings", "banner_image")

	manifest = {
		"name": title,
		"short_name": title,
		"description": "Easy to use, 100% open source Learning Management System",
		"start_url": "/lms",
		"icons": [
			{
				"src": banner_image or "/assets/lms/frontend/manifest/manifest-icon-192.maskable.png",
				"sizes": "192x192",
				"type": "image/png",
				"purpose": "maskable any",
			}
		],
	}

	return Response(json.dumps(manifest), status=200, content_type="application/manifest+json")


@frappe.whitelist()
def get_profile_details(username):
	details = frappe.db.get_value(
		"User",
		{"username": username},
		[
			"first_name",
			"last_name",
			"full_name",
			"name",
			"username",
			"user_image",
			"bio",
			"headline",
			"language",
			"cover_image",
			"open_to",
			"linkedin",
			"github",
			"twitter",
		],
		as_dict=True,
	)

	details.roles = frappe.get_roles(details.name)
	return details


@frappe.whitelist()
def get_streak_info():
	if frappe.session.user == "Guest":
		return {}

	all_dates = fetch_activity_dates(frappe.session.user)
	streak, longest_streak = calculate_streaks(all_dates)
	current_streak = calculate_current_streak(all_dates, streak)

	return {
		"current_streak": current_streak,
		"longest_streak": longest_streak,
	}


def fetch_activity_dates(user):
	doctypes = [
		"LMS Course Progress",
		"LMS Quiz Submission",
		"LMS Assignment Submission",
		"LMS Programming Exercise Submission",
	]

	all_dates = []
	for dt in doctypes:
		all_dates.extend(frappe.get_all(dt, {"member": user}, pluck="creation"))

	return sorted({d.date() if hasattr(d, "date") else d for d in all_dates})


def calculate_streaks(all_dates):
	streak = 0
	longest_streak = 0
	prev_day = None

	for d in all_dates:
		if d.weekday() in (5, 6):
			continue

		if prev_day:
			expected = prev_day + timedelta(days=1)
			while expected.weekday() in (5, 6):
				expected += timedelta(days=1)

			streak = streak + 1 if d == expected else 1
		else:
			streak = 1

		longest_streak = max(longest_streak, streak)
		prev_day = d

	return streak, longest_streak


def calculate_current_streak(all_dates, streak):
	if not all_dates:
		return 0

	last_date = all_dates[-1]
	today = getdate()

	ref_day = today
	while ref_day.weekday() in (5, 6):
		ref_day -= timedelta(days=1)

	if last_date == ref_day or last_date == ref_day - timedelta(days=1):
		return streak
	return 0


@frappe.whitelist()
def get_my_live_classes():
	my_live_classes = []
	if frappe.session.user == "Guest":
		return my_live_classes

	batches = frappe.get_all(
		"LMS Batch Enrollment",
		{
			"member": frappe.session.user,
		},
		order_by="creation desc",
		pluck="batch",
	)

	live_class_details = frappe.get_all(
		"LMS Live Class",
		filters={
			"date": [">=", getdate()],
			"batch_name": ["in", batches],
		},
		fields=[
			"name",
			"title",
			"description",
			"time",
			"date",
			"duration",
			"attendees",
			"start_url",
			"join_url",
			"owner",
		],
		limit=2,
		order_by="date",
	)

	if len(live_class_details):
		for live_class in live_class_details:
			# Get course from batch (LMS Live Class doesn't have course field)
			course = get_course_from_batch(live_class.batch_name) if live_class.get("batch_name") else None
			if course:
				live_class.course_title = frappe.db.get_value("LMS Course", course, "title")
			else:
				live_class.course_title = ""

			my_live_classes.append(live_class)

	return my_live_classes


@frappe.whitelist()
def get_created_courses():
	created_courses = []
	if frappe.session.user == "Guest":
		return created_courses

	# Check if user is Admin (Moderator role) - they see all courses
	is_admin = "Moderator" in frappe.get_roles(frappe.session.user)

	Course = frappe.qb.DocType("LMS Course")

	if is_admin:
		# Admin sees all courses
		query = (
			frappe.qb.from_(Course)
			.select(Course.name)
			.orderby(Course.published_on, order=frappe.qb.desc)
			.limit(3)
		)
	else:
		# Course Creator sees only courses where they are an instructor
		CourseInstructor = frappe.qb.DocType("Course Instructor")
		query = (
			frappe.qb.from_(CourseInstructor)
			.join(Course)
			.on(CourseInstructor.parent == Course.name)
			.select(Course.name)
			.where(CourseInstructor.instructor == frappe.session.user)
			.orderby(Course.published_on, order=frappe.qb.desc)
			.limit(3)
		)

	results = query.run(as_dict=True)
	courses = [row["name"] for row in results]

	for course in courses:
		course_details = get_course_details(course)
		created_courses.append(course_details)

	return created_courses


@frappe.whitelist()
def get_created_batches():
	created_batches = []
	if frappe.session.user == "Guest":
		return created_batches

	# Check if user is Admin (Moderator role) - they see all batches
	is_admin = "Moderator" in frappe.get_roles(frappe.session.user)

	Batch = frappe.qb.DocType("LMS Batch")

	if is_admin:
		# Admin sees all upcoming batches
		query = (
			frappe.qb.from_(Batch)
			.select(Batch.name)
			.where(Batch.start_date >= getdate())
			.orderby(Batch.start_date, order=frappe.qb.asc)
			.limit(4)
		)
	else:
		# Course Creator sees only batches where they are an instructor
		CourseInstructor = frappe.qb.DocType("Course Instructor")
		query = (
			frappe.qb.from_(CourseInstructor)
			.join(Batch)
			.on(CourseInstructor.parent == Batch.name)
			.select(Batch.name)
			.where(CourseInstructor.instructor == frappe.session.user)
			.where(Batch.start_date >= getdate())
			.orderby(Batch.start_date, order=frappe.qb.asc)
			.limit(4)
		)

	results = query.run(as_dict=True)
	batches = [row["name"] for row in results]

	for batch in batches:
		batch_details = get_batch_details(batch)
		created_batches.append(batch_details)

	return created_batches


@frappe.whitelist()
def get_admin_live_classes():
	if frappe.session.user == "Guest":
		return []

	# Check if user is Admin (Moderator role) - they see all live classes
	is_admin = "Moderator" in frappe.get_roles(frappe.session.user)

	LMSLiveClass = frappe.qb.DocType("LMS Live Class")

	if is_admin:
		# Admin sees all upcoming live classes
		query = (
			frappe.qb.from_(LMSLiveClass)
			.select(
				LMSLiveClass.name,
				LMSLiveClass.title,
				LMSLiveClass.description,
				LMSLiveClass.time,
				LMSLiveClass.date,
				LMSLiveClass.duration,
				LMSLiveClass.attendees,
				LMSLiveClass.start_url,
				LMSLiveClass.join_url,
				LMSLiveClass.owner,
			)
			.where(LMSLiveClass.date >= getdate())
			.orderby(LMSLiveClass.date, order=frappe.qb.asc)
			.limit(4)
		)
	else:
		# Course Creator sees only live classes from batches where they are an instructor
		CourseInstructor = frappe.qb.DocType("Course Instructor")
		query = (
			frappe.qb.from_(CourseInstructor)
			.join(LMSLiveClass)
			.on(CourseInstructor.parent == LMSLiveClass.batch_name)
			.select(
				LMSLiveClass.name,
				LMSLiveClass.title,
				LMSLiveClass.description,
				LMSLiveClass.time,
				LMSLiveClass.date,
				LMSLiveClass.duration,
				LMSLiveClass.attendees,
				LMSLiveClass.start_url,
				LMSLiveClass.join_url,
				LMSLiveClass.owner,
			)
			.where(CourseInstructor.instructor == frappe.session.user)
			.where(LMSLiveClass.date >= getdate())
			.orderby(LMSLiveClass.date, order=frappe.qb.asc)
			.limit(4)
		)

	results = query.run(as_dict=True)
	return results


@frappe.whitelist()
def get_admin_evals():
	if frappe.session.user == "Guest":
		return []

	# Check if user is Admin (Moderator role) - they see all evaluations
	is_admin = "Moderator" in frappe.get_roles(frappe.session.user)

	filters = {
		"date": [">=", getdate()],
	}

	# Course Creator only sees evaluations where they are the evaluator
	if not is_admin:
		filters["evaluator"] = frappe.session.user

	evals = frappe.get_all(
		"LMS Certificate Request",
		filters,
		[
			"name",
			"date",
			"start_time",
			"course",
			"evaluator",
			"google_meet_link",
			"member",
			"member_name",
		],
		limit=4,
		order_by="date asc",
	)

	for evaluation in evals:
		evaluation.course_title = frappe.db.get_value("LMS Course", evaluation.course, "title")

	return evals


@frappe.whitelist()
def get_my_courses():
	my_courses = []
	if frappe.session.user == "Guest":
		return my_courses

	courses = get_my_latest_courses()

	if not len(courses):
		courses = get_featured_home_courses()

	if not len(courses):
		courses = get_popular_courses()

	for course in courses:
		my_courses.append(get_course_details(course))

	return my_courses


def get_my_latest_courses():
	return frappe.get_all(
		"LMS Enrollment",
		{
			"member": frappe.session.user,
		},
		order_by="modified desc",
		limit=3,
		pluck="course",
	)


def get_featured_home_courses():
	return frappe.get_all(
		"LMS Course",
		{"published": 1, "featured": 1},
		order_by="published_on desc",
		limit=3,
		pluck="name",
	)


def get_popular_courses():
	return frappe.get_all(
		"LMS Course",
		{
			"published": 1,
		},
		order_by="enrollments desc",
		limit=3,
		pluck="name",
	)


@frappe.whitelist()
def get_my_batches():
	my_batches = []
	if frappe.session.user == "Guest":
		return my_batches

	batches = get_my_latest_batches()

	if not len(batches):
		batches = get_upcoming_batches()

	for batch in batches:
		batch_details = get_batch_details(batch)
		if batch_details:
			my_batches.append(batch_details)

	return my_batches


def get_my_latest_batches():
	return frappe.get_all(
		"LMS Batch Enrollment",
		{
			"member": frappe.session.user,
		},
		order_by="creation desc",
		limit=4,
		pluck="batch",
	)


def get_upcoming_batches():
	return frappe.get_all(
		"LMS Batch",
		{
			"published": 1,
			"start_date": [">=", getdate()],
		},
		order_by="start_date asc",
		limit=4,
		pluck="name",
	)


# ============================================================================
# n8n-based Vimeo Integration API
# ============================================================================


def _create_or_update_recording_from_n8n(live_class, video_id, video_url, duration=0):
	"""
	Create or update LMS Course Recording document from n8n payload.

	Args:
		live_class: LMS Live Class document
		video_id: Vimeo video ID
		video_url: Vimeo player embed URL
		duration: Video duration in seconds (optional)

	Returns:
		LMS Course Recording document
	"""
	# Check if recording already exists for this video
	existing = frappe.db.exists("LMS Course Recording", {
		"vimeo_video_id": video_id
	})

	if existing:
		recording = frappe.get_doc("LMS Course Recording", existing)
		frappe.logger().info(f"[n8n Vimeo] Updating existing recording: {recording.name}")
	else:
		recording = frappe.new_doc("LMS Course Recording")
		frappe.logger().info(f"[n8n Vimeo] Creating new recording for video: {video_id}")

	# Set all required fields
	recording.title = live_class.title
	# Get course from batch (LMS Live Class doesn't have a course field)
	course = get_course_from_batch(live_class.batch_name) if live_class.batch_name else None
	if not course:
		frappe.logger().error(f"[n8n Vimeo] No course found for live class {live_class.name} (batch: {live_class.batch_name})")
		raise ValueError(f"Cannot create recording: No course associated with live class {live_class.name}")
	recording.course = course
	recording.live_class = live_class.name
	recording.batch = live_class.batch_name
	recording.recorded_on = live_class.date
	recording.instructor = live_class.host
	recording.duration = duration if duration else 0
	recording.status = "Uploaded"  # Critical: must be "Uploaded" for students to see it

	# Vimeo details
	recording.vimeo_video_id = video_id
	recording.vimeo_uri = f"/videos/{video_id}"
	recording.vimeo_player_embed_url = video_url

	# Save with permission bypass (called from webhook context)
	recording.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.logger().info(f"[n8n Vimeo] Recording document {'updated' if existing else 'created'}: {recording.name}")

	return recording


def _find_live_class_for_vimeo_video(video_title, video_description, created_time):
	"""
	Find matching Live Class for a Vimeo video processed by n8n.

	This is a wrapper around the existing find_live_class() function in vimeo_processor,
	adapted for the n8n integration where title is already cleaned and meeting_id extracted.

	Matching strategy (4-level cascade):
	1. Match by meeting_id in description (most reliable)
	2. Match by title + date exact
	3. Match by title contains + date exact
	4. Match by title + date within ±2 hours (timezone tolerance)

	Args:
		video_title: Clean title from n8n (timestamp already removed)
		video_description: Description containing meeting ID
		created_time: Video creation datetime (datetime object or None)

	Returns:
		tuple: (live_class_doc, match_method) or (None, None)
	"""
	# Strategy 1: Match by meeting_id if present in description
	if video_description:
		import re
		meeting_id_match = re.search(r'Meeting ID[:\s]+(\d{10,12})', video_description, re.IGNORECASE)
		if meeting_id_match:
			meeting_id = meeting_id_match.group(1)
			live_class = frappe.db.get_value(
				"LMS Live Class",
				{"meeting_id": meeting_id},
				["name", "batch_name", "host", "title", "date", "time"],
				as_dict=True,
			)
			if live_class:
				frappe.logger().info(f"[n8n Vimeo] Matched by meeting_id: {meeting_id}")
				return (frappe.get_doc("LMS Live Class", live_class.name), "meeting_id")

	# If no created_time provided, can't do date-based matching
	if not created_time:
		frappe.logger().warning("[n8n Vimeo] No created_time provided, cannot perform date-based matching")
		return (None, None)

	# Convert created_time to date for matching
	if isinstance(created_time, str):
		from datetime import datetime
		try:
			created_time = get_datetime(created_time)
		except Exception as e:
			frappe.logger().error(f"[n8n Vimeo] Failed to parse created_time: {e}")
			return (None, None)

	recording_date = created_time.date() if hasattr(created_time, 'date') else created_time

	# Strategy 2: Exact title match + exact date
	live_class = frappe.db.get_value(
		"LMS Live Class",
		{"title": video_title, "date": recording_date},
		["name", "batch_name", "host", "title", "date", "time"],
		as_dict=True,
	)

	if live_class:
		frappe.logger().info(f"[n8n Vimeo] Matched by exact title + date")
		return (frappe.get_doc("LMS Live Class", live_class.name), "title_and_date")

	# Strategy 3: Title contains + exact date
	all_classes_on_date = frappe.get_all(
		"LMS Live Class",
		filters={"date": recording_date},
		fields=["name", "batch_name", "host", "title", "date", "time"],
	)

	for lc in all_classes_on_date:
		# Check if the live class title is contained in the video title or vice versa
		if video_title.lower() in lc.title.lower() or lc.title.lower() in video_title.lower():
			lc["course"] = get_course_from_batch(lc.batch_name)
			frappe.logger().info(f"[n8n Vimeo] Matched by title contains + date")
			return (frappe.get_doc("LMS Live Class", lc.name), "title_contains")

	# Strategy 4: Exact title + date within ±2 hours (for timezone edge cases)
	date_before = add_days(recording_date, -1)
	date_after = add_days(recording_date, 1)

	live_classes_nearby = frappe.get_all(
		"LMS Live Class",
		filters={
			"title": video_title,
			"date": ["between", [date_before, date_after]],
		},
		fields=["name", "batch_name", "host", "title", "date", "time"],
	)

	if live_classes_nearby:
		lc = live_classes_nearby[0]
		lc["course"] = get_course_from_batch(lc.batch_name)
		frappe.logger().info(f"[n8n Vimeo] Matched by title + date within ±1 day")
		return (frappe.get_doc("LMS Live Class", lc.name), "title_and_date_nearby")

	frappe.logger().info(f"[n8n Vimeo] No match found for title='{video_title}', date={recording_date}")
	return (None, None)


def get_course_from_batch(batch_name):
	"""Get the first course from a batch."""
	if not batch_name:
		return None

	courses = frappe.get_all(
		"Batch Course",
		filters={"parent": batch_name},
		pluck="course",
		limit=1,
	)

	return courses[0] if courses else None


def create_lesson_from_recording(live_class_name, video_url=None, recording=None):
	"""
	Auto-create a lesson in the course from a live class recording.

	This function:
	1. Finds the course(s) associated with the live class
	2. Finds or creates a "Recordings" chapter in each course
	3. Creates a lesson with the recording video embedded

	Args:
		live_class_name: Name of the LMS Live Class document
		video_url: Video embed URL (if not provided, tries to get from recording or live_class)
		recording: LMS Course Recording document (optional, for metadata like duration, instructor)

	Returns:
		list: Names of created lessons
	"""
	# Get live class details
	live_class = frappe.get_doc("LMS Live Class", live_class_name)

	# Determine video URL to use
	if not video_url:
		if recording and recording.vimeo_player_embed_url:
			video_url = recording.vimeo_player_embed_url
		else:
			# Fallback: try to read from live_class (legacy, may not exist)
			video_url = live_class.get("recording_url")

	if not video_url:
		frappe.logger().warning(
			f"[create_lesson_from_recording] No video URL provided for {live_class_name}"
		)
		return []

	# Find associated batches and courses
	batches = frappe.get_all(
		"LMS Batch",
		filters={"name": live_class.batch_name},
		fields=["name"],
	)

	if not batches:
		frappe.logger().warning(f"[n8n Vimeo] No batch found for live class {live_class_name}")
		return []

	# Get all courses from the batch
	courses = frappe.get_all(
		"Batch Course",
		filters={"parent": live_class.batch_name},
		pluck="course",
	)

	if not courses:
		frappe.logger().warning(f"[n8n Vimeo] No courses found for batch {live_class.batch_name}")
		return []

	created_lessons = []
	errors = []

	# Create lesson in each course
	for course_name in courses:
		try:
			# Find or create "Recordings" chapter
			recordings_chapter = find_or_create_recordings_chapter(course_name)

			# Check if lesson already exists for this live class
			existing_lesson = frappe.db.exists(
				"Course Lesson",
				{
					"title": live_class.title,
					"chapter": recordings_chapter.name,
				}
			)

			if existing_lesson:
				frappe.logger().info(f"Lesson already exists: {existing_lesson}, updating with video URL")
				try:
					# Update the existing lesson with the recording URL
					lesson_doc = frappe.get_doc("Course Lesson", existing_lesson)
					# Update body with new content (don't use youtube field for Vimeo)
					lesson_doc.body = _build_recording_lesson_body(live_class, video_url, recording)
					lesson_doc.save(ignore_permissions=True)
					created_lessons.append(existing_lesson)
					frappe.logger().info(f"[n8n Vimeo] Updated existing lesson {existing_lesson} in course {course_name}")
				except Exception as e:
					error_msg = f"Failed to update lesson {existing_lesson} in course {course_name}: {str(e)}"
					frappe.logger().error(f"[n8n Vimeo] {error_msg}")
					errors.append(error_msg)
					frappe.log_error(title="n8n Vimeo Lesson Update Error", message=frappe.get_traceback())
				continue

			# Create new lesson
			lesson = frappe.new_doc("Course Lesson")
			lesson.title = live_class.title
			lesson.chapter = recordings_chapter.name
			lesson.course = course_name
			lesson.include_in_preview = 0  # Not included in preview

			# Set body content with video embed using {{ Embed }} macro
			lesson.body = _build_recording_lesson_body(live_class, video_url, recording)

			lesson.insert(ignore_permissions=True)

			# Add lesson to chapter
			add_lesson_to_chapter(recordings_chapter, lesson.name)

			frappe.logger().info(f"[n8n Vimeo] Created lesson {lesson.name} in chapter {recordings_chapter.name} for course {course_name}")
			created_lessons.append(lesson.name)

		except Exception as e:
			error_msg = f"Failed to create lesson for live class {live_class_name} in course {course_name}: {str(e)}"
			frappe.logger().error(f"[n8n Vimeo] {error_msg}")
			errors.append(error_msg)
			frappe.log_error(title="n8n Vimeo Lesson Creation Error", message=frappe.get_traceback())

	# Commit all changes
	try:
		frappe.db.commit()
		if errors:
			frappe.logger().warning(f"[n8n Vimeo] Lesson creation completed with {len(errors)} error(s): {errors}")
	except Exception as e:
		frappe.logger().error(f"[n8n Vimeo] Failed to commit lesson changes: {str(e)}")
		frappe.log_error(title="Lesson Commit Error", message=frappe.get_traceback())
		# Don't raise - return what we have

	return created_lessons


def _add_vimeo_privacy_parameters(video_url):
	"""
	Add privacy parameters to Vimeo embed URL to hide sharing options and URL.

	Privacy parameters:
	- title=0: Hide video title
	- byline=0: Hide uploader name
	- portrait=0: Hide uploader portrait
	- speed=0: Hide speed controls
	- pip=0: Disable picture-in-picture
	- share=0: Hide share button
	- transparent=0: Disable transparent background

	Args:
		video_url: Original Vimeo player embed URL

	Returns:
		str: URL with privacy parameters added
	"""
	if not video_url or "vimeo.com" not in video_url.lower():
		return video_url

	# Privacy parameters to prevent sharing and hide URL
	privacy_params = [
		"title=0",
		"byline=0",
		"portrait=0",
		"speed=0",
		"pip=0",
		"share=0",
		"transparent=0"
	]

	# Check if URL already has parameters
	separator = "&" if "?" in video_url else "?"

	# Add privacy parameters
	privacy_query = separator + "&".join(privacy_params)
	secure_url = video_url + privacy_query

	frappe.logger().info(f"[Vimeo Privacy] Added privacy parameters to URL")

	return secure_url


def _build_recording_lesson_body(live_class, video_url, recording=None):
	"""
	Build the lesson body content with Vimeo embed using {{ Embed }} macro.

	Args:
		live_class: LMS Live Class document
		video_url: Vimeo embed URL
		recording: LMS Course Recording document (optional)

	Returns:
		str: Markdown content for lesson body with {{ Embed }} macro
	"""
	from frappe.utils import format_date

	# Add privacy parameters to Vimeo URL to hide sharing options and URL
	video_url = _add_vimeo_privacy_parameters(video_url)

	# Build metadata sections
	metadata_lines = []

	# Date
	if live_class.date:
		metadata_lines.append(f'**Recorded on:** {format_date(live_class.date, "medium")}')

	# Duration
	if recording and recording.duration:
		duration_formatted = recording.get("duration_formatted") or f"{recording.duration // 60} minutes"
		metadata_lines.append(f'**Duration:** {duration_formatted}')
	elif live_class.duration:
		metadata_lines.append(f'**Duration:** {live_class.duration} minutes')

	# Instructor
	if recording and recording.instructor:
		instructor_name = frappe.db.get_value("User", recording.instructor, "full_name")
		if instructor_name:
			metadata_lines.append(f'**Instructor:** {instructor_name}')

	# Build complete body using {{ Embed }} macro
	body_parts = [
		f'{{{{ Embed("{video_url}") }}}}',
		'',  # Empty line for spacing
	]

	# Add metadata
	if metadata_lines:
		body_parts.extend(metadata_lines)
		body_parts.append('')  # Empty line

	# Add description
	if live_class.description:
		body_parts.append(live_class.description)

	body = '\n\n'.join(body_parts)
	return body


def find_or_create_recordings_chapter(course_name):
	"""
	Find or create a "Recordings" chapter in a course.

	Args:
		course_name: Name of the LMS Course

	Returns:
		Course Chapter document

	Raises:
		Exception: If course doesn't exist or chapter creation fails
	"""
	if not course_name:
		raise ValueError("Course name is required to create recordings chapter")

	# Verify course exists
	if not frappe.db.exists("LMS Course", course_name):
		raise ValueError(f"Course {course_name} does not exist")

	# Look for existing "Recordings" chapter
	existing_chapter = frappe.db.get_value(
		"Course Chapter",
		{"course": course_name, "title": "Recordings"},
		["name"],
	)

	if existing_chapter:
		return frappe.get_doc("Course Chapter", existing_chapter)

	# Create new "Recordings" chapter
	try:
		chapter = frappe.new_doc("Course Chapter")
		chapter.title = "Recordings"
		chapter.course = course_name
		chapter.description = "Live class recordings from this course"
		chapter.insert(ignore_permissions=True)

		# Add chapter reference to course
		chapter_ref = frappe.new_doc("Chapter Reference")
		chapter_ref.chapter = chapter.name
		chapter_ref.parent = course_name
		chapter_ref.parenttype = "LMS Course"
		chapter_ref.parentfield = "chapters"

		# Set idx to last position
		existing_refs = frappe.get_all(
			"Chapter Reference",
			filters={"parent": course_name},
			order_by="idx desc",
			limit=1,
			pluck="idx",
		)
		chapter_ref.idx = (existing_refs[0] + 1) if existing_refs else 1

		chapter_ref.insert(ignore_permissions=True)
		frappe.db.commit()

		frappe.logger().info(f"[n8n Vimeo] Created Recordings chapter in course {course_name}")
		return chapter
	except Exception as e:
		frappe.logger().error(f"[n8n Vimeo] Failed to create Recordings chapter: {str(e)}")
		raise


def add_lesson_to_chapter(chapter, lesson_name):
	"""
	Add a lesson reference to a chapter.

	Args:
		chapter: Course Chapter document
		lesson_name: Name of the Course Lesson

	Raises:
		Exception: If lesson reference creation fails
	"""
	if not chapter or not lesson_name:
		raise ValueError("Chapter and lesson_name are required")

	# Check if lesson reference already exists
	existing_ref = frappe.db.exists(
		"Lesson Reference",
		{"parent": chapter.name, "lesson": lesson_name}
	)

	if existing_ref:
		frappe.logger().info(f"[n8n Vimeo] Lesson {lesson_name} already in chapter {chapter.name}")
		return

	# Get last idx
	existing_refs = frappe.get_all(
		"Lesson Reference",
		filters={"parent": chapter.name},
		order_by="idx desc",
		limit=1,
		pluck="idx",
	)

	# Create lesson reference
	try:
		lesson_ref = frappe.new_doc("Lesson Reference")
		lesson_ref.lesson = lesson_name
		lesson_ref.parent = chapter.name
		lesson_ref.parenttype = "Course Chapter"
		lesson_ref.parentfield = "lessons"
		lesson_ref.idx = (existing_refs[0] + 1) if existing_refs else 1
		lesson_ref.insert(ignore_permissions=True)
		frappe.logger().info(f"[n8n Vimeo] Added lesson {lesson_name} to chapter {chapter.name}")
	except Exception as e:
		frappe.logger().error(f"[n8n Vimeo] Failed to add lesson to chapter: {str(e)}")
		raise


def _validate_vimeo_n8n_payload(payload):
	"""
	Validate incoming payload from n8n for Vimeo recordings.

	Args:
		payload (dict): JSON payload from n8n

	Returns:
		list: List of validation error messages (empty if valid)
	"""
	errors = []

	# Required: video_url
	video_url = payload.get("video_url")
	if not video_url:
		errors.append("video_url is required")
	elif not isinstance(video_url, str) or "vimeo.com" not in video_url.lower():
		errors.append("video_url must be a valid Vimeo URL")

	# Required: video_id
	video_id = payload.get("video_id")
	if not video_id:
		errors.append("video_id is required")
	elif not str(video_id).isdigit():
		errors.append("video_id must be numeric")

	# Optional: created_time (validate if provided)
	created_time = payload.get("created_time")
	if created_time:
		try:
			if isinstance(created_time, (int, float)):
				# Unix timestamp - validate range
				from datetime import datetime
				datetime.fromtimestamp(created_time)
			else:
				# ISO format string - use Frappe's date parser
				get_datetime(created_time)
		except Exception as e:
			errors.append(f"created_time is invalid: {str(e)}")

	# Optional: meeting_id (validate if provided)
	meeting_id = payload.get("meeting_id")
	if meeting_id:
		meeting_id_str = str(meeting_id)
		if not (meeting_id_str.isdigit() and 10 <= len(meeting_id_str) <= 12):
			errors.append("meeting_id must be a 10-12 digit numeric string")

	return errors


@frappe.whitelist(allow_guest=True, methods=["POST"])
def process_vimeo_recording():
	"""
	Simplified API endpoint for n8n-processed Vimeo recordings.

	Architecture:
		Vimeo → n8n webhook → n8n transforms → LMS API (this endpoint)

	n8n handles:
		- Vimeo webhook signature verification
		- Vimeo API enrichment for metadata
		- Title cleaning (removes Vimeo timestamp suffix)
		- Meeting ID extraction from description

	LMS handles:
		- Request validation
		- Live Class matching (4-level cascade)
		- Recording URL update
		- Lesson creation

	Expected payload from n8n:
		{
			"video_url": "https://player.vimeo.com/video/123",
			"video_id": "123",
			"created_time": "2026-01-11T15:46:00Z" or 1736609160,
			"meeting_id": "12345678901",  // optional
			"title": "Live Class on Python",  // optional, already cleaned
			"description": "Meeting info...",  // optional
			"duration": 3600  // optional, seconds
		}

	Returns:
		Success response (200):
			{
				"status": "success",
				"message": "Recording updated for LMS-LC-00123",
				"live_class": "LMS-LC-00123",
				"lesson_created": true,
				"matched_by": "meeting_id"
			}

		No match response (200):
			{
				"status": "success",
				"message": "No matching live class found",
				"matched": false
			}

		Error response (200 with error status):
			{
				"status": "error",
				"message": "video_url is required",
				"code": "VALIDATION_ERROR"
			}
	"""
	try:
		# Disable CSRF for external n8n calls
		frappe.flags.ignore_csrf = True

		# Parse request body
		if frappe.request.data:
			request_data = frappe.request.data
			if isinstance(request_data, bytes):
				request_data = request_data.decode('utf-8')
			payload = json.loads(request_data)
		else:
			frappe.logger().error("[n8n Vimeo] No data received in request")
			return {
				"status": "error",
				"message": "No data received",
				"code": "NO_DATA"
			}

		frappe.logger().info(f"[n8n Vimeo] Received payload: {json.dumps(payload, indent=2)}")

		# Validate payload
		validation_errors = _validate_vimeo_n8n_payload(payload)
		if validation_errors:
			error_msg = "; ".join(validation_errors)
			frappe.logger().error(f"[n8n Vimeo] Validation failed: {error_msg}")
			return {
				"status": "error",
				"message": error_msg,
				"code": "VALIDATION_ERROR"
			}

		# Extract and normalize data
		video_url = payload.get("video_url")
		video_id = str(payload.get("video_id"))
		title = payload.get("title", "")
		description = payload.get("description", "")
		duration = payload.get("duration", 0)

		# Parse created_time (handle both ISO and Unix formats)
		created_time = payload.get("created_time")
		if created_time:
			if isinstance(created_time, (int, float)):
				# Unix timestamp
				from datetime import datetime
				created_time = datetime.fromtimestamp(created_time)
				frappe.logger().info(f"[n8n Vimeo] Converted Unix timestamp to: {created_time}")
			else:
				# ISO format - use Frappe's date parser
				created_time = get_datetime(created_time)
				frappe.logger().info(f"[n8n Vimeo] Parsed ISO timestamp: {created_time}")
		else:
			frappe.logger().warning("[n8n Vimeo] No created_time provided, matching may be less accurate")

		# Log incoming video info
		frappe.logger().info(f"[n8n Vimeo] Processing video: ID={video_id}, URL={video_url}, Title='{title}'")

		# Find matching Live Class using the wrapper function
		live_class, match_method = _find_live_class_for_vimeo_video(
			video_title=title,
			video_description=description,
			created_time=created_time
		)

		if not live_class:
			frappe.logger().info("[n8n Vimeo] No matching Live Class found")
			return {
				"status": "success",
				"message": "No matching live class found (might not be an LMS recording)",
				"matched": False
			}

		frappe.logger().info(f"[n8n Vimeo] Matched Live Class: {live_class.name} using {match_method}")

		# Create/update LMS Course Recording document
		recording = None
		try:
			recording = _create_or_update_recording_from_n8n(
				live_class=live_class,
				video_id=video_id,
				video_url=video_url,
				duration=duration
			)
			frappe.logger().info(f"[n8n Vimeo] Recording document created/updated: {recording.name}")
		except ValueError as e:
			# This is a validation error (e.g., missing course) - should be returned as error
			frappe.logger().error(f"[n8n Vimeo] Validation error creating recording: {str(e)}")
			frappe.log_error(title="n8n Recording Validation Error", message=frappe.get_traceback())
			return {
				"status": "error",
				"message": str(e),
				"code": "VALIDATION_ERROR"
			}
		except Exception as e:
			frappe.logger().error(f"[n8n Vimeo] Failed to create recording document: {str(e)}")
			frappe.log_error(title="n8n Recording Creation Error", message=frappe.get_traceback())
			# Continue anyway - lesson creation should still work, but log the error

		# Create lesson from recording
		lesson_created = False
		lesson_error = None
		try:
			lessons = create_lesson_from_recording(
				live_class_name=live_class.name,
				video_url=video_url,
				recording=recording  # Pass the recording document we created
			)
			lesson_created = len(lessons) > 0
			if lesson_created:
				frappe.logger().info(f"[n8n Vimeo] Created/updated {len(lessons)} lesson(s) for {live_class.name}")
			else:
				frappe.logger().warning(f"[n8n Vimeo] No lessons created for {live_class.name} (check logs for details)")
		except Exception as e:
			lesson_error = str(e)
			frappe.logger().error(f"[n8n Vimeo] Could not create lesson: {lesson_error}")
			frappe.log_error(title="Lesson Creation Error", message=frappe.get_traceback())

		# Commit changes to database
		try:
			frappe.db.commit()
		except Exception as e:
			frappe.logger().error(f"[n8n Vimeo] Database commit failed: {str(e)}")
			frappe.log_error(title="Database Commit Error", message=frappe.get_traceback())
			# Try to rollback
			frappe.db.rollback()
			return {
				"status": "error",
				"message": f"Failed to save changes to database: {str(e)}",
				"code": "DATABASE_ERROR"
			}

		return {
			"status": "success",
			"message": f"Recording updated with Vimeo URL for {live_class.name}",
			"live_class": live_class.name,
			"recording": recording.name if recording else None,
			"video_url": video_url,
			"lesson_created": lesson_created,
			"lesson_error": lesson_error if not lesson_created and lesson_error else None,
			"matched_by": match_method
		}

	except json.JSONDecodeError as e:
		frappe.logger().error(f"[n8n Vimeo] JSON decode error: {str(e)}")
		return {
			"status": "error",
			"message": "Invalid JSON in request body",
			"code": "JSON_ERROR"
		}
	except Exception as e:
		error_msg = str(e)
		error_traceback = frappe.get_traceback()
		frappe.logger().error(f"[n8n Vimeo] Unexpected error: {error_msg}")
		frappe.log_error(title="n8n Vimeo Recording Error", message=error_traceback)
		return {
			"status": "error",
			"message": f"Error processing recording: {error_msg}",
			"code": "PROCESSING_ERROR",
			"details": error_traceback.split('\n')[-5:] if error_traceback else None  # Last 5 lines of traceback
		}


# ============================================================================
# Course Recordings API
# ============================================================================


@frappe.whitelist()
def get_course_recordings(course, start=0, page_length=20):
	"""
	Get recordings for a course.
	Only returns recordings the user has access to view.

	Args:
		course: Course name
		start: Pagination start
		page_length: Number of records to return

	Returns:
		dict with recordings list and total_count
	"""
	if not course:
		frappe.throw(_("Course is required"))

	# Check access
	if not has_recording_access(course):
		frappe.throw(_("You do not have access to view recordings for this course"))

	user = frappe.session.user
	user_roles = frappe.get_roles(user)

	# Build filters based on role
	filters = {"course": course}

	# Students only see Uploaded recordings
	if "LMS Student" in user_roles and "Moderator" not in user_roles and "Course Creator" not in user_roles:
		filters["status"] = "Uploaded"

	# Get recordings
	recordings = frappe.get_all(
		"LMS Course Recording",
		filters=filters,
		fields=[
			"name",
			"title",
			"status",
			"recorded_on",
			"duration",
			"duration_formatted",
			"thumbnail",
			"vimeo_player_embed_url",
			"instructor",
			"live_class",
		],
		order_by="recorded_on desc",
		start=cint(start),
		limit_page_length=cint(page_length),
	)

	# Get instructor names
	for recording in recordings:
		if recording.instructor:
			recording.instructor_name = frappe.db.get_value(
				"User", recording.instructor, "full_name"
			)

	# Get total count
	total_count = frappe.db.count("LMS Course Recording", filters)

	return {
		"recordings": recordings,
		"total_count": total_count,
	}


@frappe.whitelist()
def get_recording_embed(recording_name):
	"""
	Get the Vimeo embed URL for a specific recording.
	Performs access control check before returning URL.

	Args:
		recording_name: Recording document name

	Returns:
		dict with embed_url and recording details
	"""
	if not frappe.db.exists("LMS Course Recording", recording_name):
		frappe.throw(_("Recording not found"))

	recording = frappe.get_doc("LMS Course Recording", recording_name)

	# Check access
	if not has_recording_access(recording.course):
		frappe.throw(_("You do not have access to view this recording"))

	# Check if recording is available
	if recording.status != "Uploaded":
		frappe.throw(_("Recording is not available for viewing"))

	return {
		"name": recording.name,
		"title": recording.title,
		"embed_url": recording.vimeo_player_embed_url,
		"duration": recording.duration,
		"duration_formatted": recording.duration_formatted,
		"recorded_on": recording.recorded_on,
	}


@frappe.whitelist()
def trigger_recording_sync(live_class=None):
	"""
	Manually trigger sync of recordings from Vimeo.

	With the native Vimeo-Zoom integration, recordings are automatically
	uploaded to Vimeo. This function triggers a check for new recordings.

	Args:
		live_class: Optional live class document name to check
	"""
	frappe.only_for(["Moderator", "Course Creator"])

	# If a specific live class is provided, check if recording exists
	if live_class:
		if not frappe.db.exists("LMS Live Class", live_class):
			frappe.throw(_("Live class not found"))

		existing = frappe.db.exists("LMS Course Recording", {"live_class": live_class})
		if existing:
			recording = frappe.get_doc("LMS Course Recording", existing)
			return {
				"status": "exists",
				"recording": existing,
				"vimeo_status": recording.status,
			}

	# Trigger Vimeo folder poll to check for new recordings
	from lms.lms.doctype.lms_course_recording.vimeo_processor import poll_vimeo_folder

	frappe.enqueue(
		poll_vimeo_folder,
		queue="default",
		timeout=300,
	)

	return {
		"status": "sync_triggered",
		"message": "Vimeo sync has been triggered. New recordings will appear shortly if available.",
	}


@frappe.whitelist()
def get_recording_status(recording_name):
	"""
	Get the current upload/processing status of a recording.

	Args:
		recording_name: Recording document name

	Returns:
		dict with status and details
	"""
	if not frappe.db.exists("LMS Course Recording", recording_name):
		frappe.throw(_("Recording not found"))

	recording = frappe.db.get_value(
		"LMS Course Recording",
		recording_name,
		["name", "title", "status", "error_message", "vimeo_player_embed_url"],
		as_dict=True,
	)

	# Only show error message to admins/creators
	user_roles = frappe.get_roles(frappe.session.user)
	if "Moderator" not in user_roles and "Course Creator" not in user_roles:
		recording.error_message = None

	return recording


def has_recording_access(course):
	"""
	Check if current user has access to view recordings for a course.
	"""
	user = frappe.session.user

	if user == "Administrator":
		return True

	user_roles = frappe.get_roles(user)

	# Moderator has full access
	if "Moderator" in user_roles:
		return True

	# Course instructor has access
	if frappe.db.exists(
		"Course Instructor", {"parent": course, "instructor": user}
	):
		return True

	# Teacher assigned to a batch with this course
	if "Teacher" in user_roles:
		batches_with_course = frappe.get_all(
			"Batch Course", filters={"course": course}, pluck="parent"
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

	# Enrolled student has access (with batch enrollment status check)
	enrollment = frappe.db.get_value(
		"LMS Enrollment",
		{"course": course, "member": user},
		["name", "enrollment_from_batch"],
		as_dict=True
	)
	if enrollment:
		# If enrollment is from a batch, verify batch enrollment is still active
		if enrollment.enrollment_from_batch:
			batch_enrollment_active = frappe.db.exists(
				"LMS Batch Enrollment",
				{
					"member": user,
					"batch": enrollment.enrollment_from_batch,
					"status": ["in", ["Active", "Extended"]]
				}
			)
			if batch_enrollment_active:
				return True
		else:
			# Direct course enrollment (not from batch)
			return True

	return False


@frappe.whitelist(allow_guest=True)
def get_openapi_spec():
	"""
	Returns the OpenAPI 3.0 specification as JSON.
	Reads from YAML files and converts to JSON for Swagger UI.

	Returns:
		dict: OpenAPI specification as dictionary
	"""
	import yaml
	import os

	spec_path = os.path.join(
		frappe.get_app_path("lms"),
		"openapi",
		"spec.yaml"
	)

	try:
		with open(spec_path, 'r', encoding='utf-8') as f:
			spec = yaml.safe_load(f)
		return spec
	except FileNotFoundError:
		frappe.throw(_("OpenAPI specification file not found"))
	except yaml.YAMLError as e:
		frappe.log_error(f"YAML parsing error: {str(e)}", "OpenAPI Spec Error")
		frappe.throw(_("Error parsing OpenAPI specification"))
	except Exception as e:
		frappe.log_error(f"Error loading OpenAPI spec: {str(e)}", "OpenAPI Spec Error")
		frappe.throw(_("Error loading OpenAPI specification"))


# ============================================================================
# TIME-LIMITED BATCH ENROLLMENT APIs
# ============================================================================

@frappe.whitelist()
def enroll_student_with_duration(batch, member, access_duration_days, access_start_date=None, payment_name=None):
	"""
	Enroll a student into a batch with time-limited access.

	Args:
		batch (str): The batch ID to enroll in
		member (str): The user ID or email of the student to enroll
		access_duration_days (int): Number of days the student will have access
		access_start_date (str, optional): When access starts (defaults to today)
		payment_name (str, optional): Payment document name for paid batches

	Returns:
		dict: Enrollment details including enrollment ID, access dates, and status
	"""
	# Validate inputs
	if not batch:
		frappe.throw(_("Batch is required"))

	if not member:
		frappe.throw(_("Member is required"))

	if not access_duration_days:
		frappe.throw(_("Access duration (days) is required"))

	access_duration_days = cint(access_duration_days)
	if access_duration_days <= 0:
		frappe.throw(_("Access duration must be a positive number"))

	# Validate batch exists
	if not frappe.db.exists("LMS Batch", batch):
		frappe.throw(_("The specified batch does not exist."))

	# Validate member exists
	if not frappe.db.exists("User", member):
		frappe.throw(_("The specified user does not exist."))

	# Check permissions
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Moderator", "Course Creator", "Batch Evaluator", "System Manager"]):
		frappe.throw(_("You do not have permission to enroll students."))

	# Check for existing enrollment
	existing = frappe.db.exists("LMS Batch Enrollment", {"batch": batch, "member": member})
	if existing:
		frappe.throw(_("This member is already enrolled in this batch."))

	# Get payment details if provided
	payment_doc = None
	if payment_name:
		payment_doc = frappe.get_doc("LMS Payment", payment_name)

	# Set access start date
	if not access_start_date:
		access_start_date = nowdate()

	# Calculate access end date
	access_end_date = add_days(access_start_date, access_duration_days)

	# Create enrollment
	enrollment = frappe.new_doc("LMS Batch Enrollment")
	enrollment.update({
		"member": member,
		"batch": batch,
		"is_time_limited": 1,
		"enrollment_date": nowdate(),
		"access_start_date": access_start_date,
		"access_end_date": access_end_date,
		"access_duration_days": access_duration_days,
		"status": "Active"
	})

	if payment_doc:
		enrollment.update({
			"payment": payment_doc.name,
			"source": payment_doc.source if hasattr(payment_doc, "source") else None,
		})

	enrollment.insert()

	return {
		"success": True,
		"message": _("Student enrolled successfully with time-limited access"),
		"enrollment": enrollment.name,
		"member": member,
		"batch": batch,
		"access_start_date": str(access_start_date),
		"access_end_date": str(access_end_date),
		"access_duration_days": access_duration_days,
		"status": enrollment.status
	}


@frappe.whitelist()
def extend_batch_access(enrollment, extension_days, reason=None):
	"""
	Extend a student's batch access by specified number of days.

	Args:
		enrollment (str): The enrollment ID
		extension_days (int): Number of days to extend the access
		reason (str, optional): Reason for the extension

	Returns:
		dict: Extension details including previous and new end dates
	"""
	# Validate inputs
	if not enrollment:
		frappe.throw(_("Enrollment ID is required"))

	if not extension_days:
		frappe.throw(_("Extension days is required"))

	extension_days = cint(extension_days)
	if extension_days <= 0:
		frappe.throw(_("Extension days must be a positive number"))

	# Check permissions
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Moderator", "Course Creator", "Batch Evaluator", "System Manager"]):
		frappe.throw(_("You do not have permission to extend enrollment access."))

	# Get enrollment
	if not frappe.db.exists("LMS Batch Enrollment", enrollment):
		frappe.throw(_("The specified enrollment does not exist."))

	enrollment_doc = frappe.get_doc("LMS Batch Enrollment", enrollment)

	# Validate it's a time-limited enrollment
	if not enrollment_doc.is_time_limited:
		frappe.throw(_("This enrollment is not time-limited. Extension is not applicable."))

	# Check if enrollment was manually removed
	if enrollment_doc.status == "Manually Removed":
		frappe.throw(_("Cannot extend access for a manually removed enrollment. Please create a new enrollment instead."))

	# Extend access
	result = enrollment_doc.extend_access(
		extension_days=extension_days,
		reason=reason,
		extended_by=frappe.session.user
	)

	return {
		"success": True,
		"message": _("Access extended successfully by {0} days").format(extension_days),
		"enrollment": enrollment,
		"previous_end_date": result["previous_end_date"],
		"new_end_date": result["new_end_date"],
		"extended_count": result["extended_count"],
		"extended_by": frappe.session.user
	}


@frappe.whitelist()
def remove_student_from_batch(enrollment, reason=None):
	"""
	Manually remove a student from a batch.

	Args:
		enrollment (str): The enrollment ID
		reason (str, optional): Reason for removal

	Returns:
		dict: Removal confirmation
	"""
	# Validate inputs
	if not enrollment:
		frappe.throw(_("Enrollment ID is required"))

	# Check permissions
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Moderator", "Course Creator", "Batch Evaluator", "System Manager"]):
		frappe.throw(_("You do not have permission to remove students from batches."))

	# Get enrollment
	if not frappe.db.exists("LMS Batch Enrollment", enrollment):
		frappe.throw(_("The specified enrollment does not exist."))

	enrollment_doc = frappe.get_doc("LMS Batch Enrollment", enrollment)

	# Check if already removed
	if enrollment_doc.status == "Manually Removed":
		frappe.throw(_("This enrollment has already been removed."))

	# Get member info before removal
	member = enrollment_doc.member
	member_name = enrollment_doc.member_name
	batch = enrollment_doc.batch

	# Remove from batch
	enrollment_doc.remove_from_batch(reason=reason)

	return {
		"success": True,
		"message": _("Student removed from batch successfully"),
		"enrollment": enrollment,
		"member": member,
		"member_name": member_name,
		"batch": batch,
		"reason": reason,
		"removed_by": frappe.session.user
	}


@frappe.whitelist()
def get_enrollment_status(enrollment):
	"""
	Get detailed status of an enrollment including access information.

	Args:
		enrollment (str): The enrollment ID

	Returns:
		dict: Detailed enrollment information
	"""
	# Validate inputs
	if not enrollment:
		frappe.throw(_("Enrollment ID is required"))

	# Get enrollment
	if not frappe.db.exists("LMS Batch Enrollment", enrollment):
		frappe.throw(_("The specified enrollment does not exist."))

	enrollment_doc = frappe.get_doc("LMS Batch Enrollment", enrollment)

	# Calculate days remaining
	days_remaining = None
	is_expired = False
	if enrollment_doc.is_time_limited and enrollment_doc.access_end_date:
		end_date = getdate(enrollment_doc.access_end_date)
		today = getdate(nowdate())
		days_remaining = (end_date - today).days
		is_expired = days_remaining < 0

	# Get extension history
	extension_history = []
	for ext in enrollment_doc.extension_history:
		extension_history.append({
			"extended_on": str(ext.extended_on) if ext.extended_on else None,
			"extended_by": ext.extended_by,
			"previous_end_date": str(ext.previous_end_date) if ext.previous_end_date else None,
			"new_end_date": str(ext.new_end_date) if ext.new_end_date else None,
			"extension_days": ext.extension_days,
			"reason": ext.reason
		})

	return {
		"enrollment": enrollment_doc.name,
		"member": enrollment_doc.member,
		"member_name": enrollment_doc.member_name,
		"batch": enrollment_doc.batch,
		"status": enrollment_doc.status,
		"is_time_limited": enrollment_doc.is_time_limited,
		"enrollment_date": str(enrollment_doc.enrollment_date) if enrollment_doc.enrollment_date else None,
		"access_start_date": str(enrollment_doc.access_start_date) if enrollment_doc.access_start_date else None,
		"access_end_date": str(enrollment_doc.access_end_date) if enrollment_doc.access_end_date else None,
		"access_duration_days": enrollment_doc.access_duration_days,
		"days_remaining": days_remaining,
		"is_expired": is_expired,
		"has_active_access": enrollment_doc.has_active_access(),
		"extended_count": enrollment_doc.extended_count or 0,
		"last_extended_on": str(enrollment_doc.last_extended_on) if enrollment_doc.last_extended_on else None,
		"removal_reason": enrollment_doc.removal_reason,
		"extension_history": extension_history
	}


@frappe.whitelist()
def get_expiring_enrollments(batch=None, days_until_expiry=7):
	"""
	Get enrollments that are expiring within the specified number of days.

	Args:
		batch (str, optional): Filter by specific batch
		days_until_expiry (int, optional): Number of days to look ahead (default: 7)

	Returns:
		list: List of enrollments expiring soon
	"""
	# Check permissions
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Moderator", "Course Creator", "Batch Evaluator", "System Manager"]):
		frappe.throw(_("You do not have permission to view expiring enrollments."))

	days_until_expiry = cint(days_until_expiry)
	if days_until_expiry < 0:
		days_until_expiry = 7

	today = getdate(nowdate())
	expiry_date = add_days(today, days_until_expiry)

	filters = {
		"is_time_limited": 1,
		"status": ["in", ["Active", "Extended"]],
		"access_end_date": ["between", [today, expiry_date]]
	}

	if batch:
		filters["batch"] = batch

	enrollments = frappe.get_all(
		"LMS Batch Enrollment",
		filters=filters,
		fields=[
			"name",
			"member",
			"member_name",
			"batch",
			"status",
			"access_start_date",
			"access_end_date",
			"access_duration_days",
			"extended_count"
		],
		order_by="access_end_date asc"
	)

	# Add days remaining to each enrollment
	for enrollment in enrollments:
		if enrollment.access_end_date:
			end_date = getdate(enrollment.access_end_date)
			enrollment["days_remaining"] = (end_date - today).days
			enrollment["access_end_date"] = str(enrollment.access_end_date)
			enrollment["access_start_date"] = str(enrollment.access_start_date) if enrollment.access_start_date else None

		# Get batch title
		enrollment["batch_title"] = frappe.db.get_value("LMS Batch", enrollment.batch, "title")

	return {
		"success": True,
		"total": len(enrollments),
		"days_until_expiry": days_until_expiry,
		"enrollments": enrollments
	}


@frappe.whitelist()
def bulk_enroll_students_with_duration(batch, members, access_duration_days, access_start_date=None):
	"""
	Enroll multiple students into a batch with time-limited access.

	Args:
		batch (str): The batch ID to enroll in
		members (list/str): List of user IDs or emails to enroll (can be JSON string)
		access_duration_days (int): Number of days each student will have access
		access_start_date (str, optional): When access starts (defaults to today)

	Returns:
		dict: Summary of enrollments created
	"""
	# Validate inputs
	if not batch:
		frappe.throw(_("Batch is required"))

	if not members:
		frappe.throw(_("Members list is required"))

	# Parse members if JSON string
	if isinstance(members, str):
		try:
			members = json.loads(members)
		except json.JSONDecodeError:
			# Try comma-separated format
			members = [m.strip() for m in members.split(",") if m.strip()]

	if not isinstance(members, list) or len(members) == 0:
		frappe.throw(_("Members must be a non-empty list"))

	if not access_duration_days:
		frappe.throw(_("Access duration (days) is required"))

	access_duration_days = cint(access_duration_days)
	if access_duration_days <= 0:
		frappe.throw(_("Access duration must be a positive number"))

	# Check permissions
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Moderator", "Course Creator", "Batch Evaluator", "System Manager"]):
		frappe.throw(_("You do not have permission to enroll students."))

	# Validate batch exists
	if not frappe.db.exists("LMS Batch", batch):
		frappe.throw(_("The specified batch does not exist."))

	# Set access start date
	if not access_start_date:
		access_start_date = nowdate()

	# Calculate access end date
	access_end_date = add_days(access_start_date, access_duration_days)

	results = {
		"success": [],
		"failed": [],
		"skipped": []
	}

	for member in members:
		try:
			# Validate member exists
			if not frappe.db.exists("User", member):
				results["failed"].append({
					"member": member,
					"reason": "User does not exist"
				})
				continue

			# Check for existing enrollment
			existing = frappe.db.exists("LMS Batch Enrollment", {"batch": batch, "member": member})
			if existing:
				results["skipped"].append({
					"member": member,
					"reason": "Already enrolled",
					"enrollment": existing
				})
				continue

			# Create enrollment
			enrollment = frappe.new_doc("LMS Batch Enrollment")
			enrollment.update({
				"member": member,
				"batch": batch,
				"is_time_limited": 1,
				"enrollment_date": nowdate(),
				"access_start_date": access_start_date,
				"access_end_date": access_end_date,
				"access_duration_days": access_duration_days,
				"status": "Active"
			})
			enrollment.insert()

			results["success"].append({
				"member": member,
				"enrollment": enrollment.name
			})

		except Exception as e:
			results["failed"].append({
				"member": member,
				"reason": str(e)
			})

	return {
		"success": True,
		"message": _("Bulk enrollment completed"),
		"batch": batch,
		"access_start_date": str(access_start_date),
		"access_end_date": str(access_end_date),
		"access_duration_days": access_duration_days,
		"total_processed": len(members),
		"enrolled": len(results["success"]),
		"skipped": len(results["skipped"]),
		"failed": len(results["failed"]),
		"details": results
	}


@frappe.whitelist()
def check_batch_enrollment_access(batch, member=None):
	"""
	Check if a user has active access to a batch.

	Args:
		batch (str): The batch ID
		member (str, optional): The user ID (defaults to current user)

	Returns:
		dict: Access status information
	"""
	if not batch:
		frappe.throw(_("Batch is required"))

	if not member:
		member = frappe.session.user

	# Import the check function
	from lms.lms.doctype.lms_batch_enrollment.lms_batch_enrollment import check_batch_access

	has_access = check_batch_access(member, batch)

	# Get enrollment details if exists
	enrollment = frappe.db.get_value(
		"LMS Batch Enrollment",
		{"member": member, "batch": batch},
		["name", "status", "is_time_limited", "access_end_date", "access_start_date"],
		as_dict=True
	)

	days_remaining = None
	if enrollment and enrollment.is_time_limited and enrollment.access_end_date:
		end_date = getdate(enrollment.access_end_date)
		today = getdate(nowdate())
		days_remaining = (end_date - today).days

	return {
		"has_access": has_access,
		"member": member,
		"batch": batch,
		"enrollment": enrollment.name if enrollment else None,
		"status": enrollment.status if enrollment else None,
		"is_time_limited": enrollment.is_time_limited if enrollment else None,
		"access_end_date": str(enrollment.access_end_date) if enrollment and enrollment.access_end_date else None,
		"days_remaining": days_remaining
	}


@frappe.whitelist()
def get_batch_enrollments(batch, status=None, is_time_limited=None, limit=100, offset=0):
	"""
	Get all enrollments for a batch with optional filters.

	Args:
		batch (str): The batch ID
		status (str, optional): Filter by status (Active, Expired, Extended, Manually Removed)
		is_time_limited (int, optional): Filter by time-limited flag (0 or 1)
		limit (int, optional): Max results (default 100)
		offset (int, optional): Pagination offset

	Returns:
		dict: List of enrollments with pagination info
	"""
	# Check permissions
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Moderator", "Course Creator", "Batch Evaluator", "System Manager"]):
		frappe.throw(_("You do not have permission to view batch enrollments."))

	if not batch:
		frappe.throw(_("Batch is required"))

	if not frappe.db.exists("LMS Batch", batch):
		frappe.throw(_("The specified batch does not exist."))

	filters = {"batch": batch}

	if status:
		filters["status"] = status

	if is_time_limited is not None:
		filters["is_time_limited"] = cint(is_time_limited)

	# Get total count
	total = frappe.db.count("LMS Batch Enrollment", filters)

	# Get enrollments
	enrollments = frappe.get_all(
		"LMS Batch Enrollment",
		filters=filters,
		fields=[
			"name", "member", "member_name", "status",
			"is_time_limited", "enrollment_date",
			"access_start_date", "access_end_date",
			"access_duration_days", "extended_count"
		],
		order_by="enrollment_date desc",
		limit_page_length=cint(limit),
		limit_start=cint(offset)
	)

	# Add computed fields
	today = getdate(nowdate())
	for enrollment in enrollments:
		if enrollment.is_time_limited and enrollment.access_end_date:
			end_date = getdate(enrollment.access_end_date)
			enrollment["days_remaining"] = (end_date - today).days
			enrollment["is_expired"] = enrollment["days_remaining"] < 0
		enrollment["access_end_date"] = str(enrollment.access_end_date) if enrollment.access_end_date else None
		enrollment["access_start_date"] = str(enrollment.access_start_date) if enrollment.access_start_date else None
		enrollment["enrollment_date"] = str(enrollment.enrollment_date) if enrollment.enrollment_date else None

	return {
		"success": True,
		"batch": batch,
		"total": total,
		"limit": limit,
		"offset": offset,
		"enrollments": enrollments
	}
