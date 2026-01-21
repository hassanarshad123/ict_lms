import frappe


def execute():
	"""
	Allow Course Creator, Moderator, and Batch Evaluator roles to read User doctype.
	This is needed for the student dropdown in batch management to show all users.
	"""
	from lms.install import give_user_permission_to_lms_roles

	give_user_permission_to_lms_roles()
