import re
from datetime import datetime

import frappe
from frappe import _


# Constraints
MAX_FILE_SIZE_MB = 5
MAX_ROWS = 500
REQUIRED_COLUMNS = {"first_name", "last_name", "email", "batch_id", "enrolled_time", "expiry_time"}
OPTIONAL_COLUMNS = {"phone"}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_columns(columns):
	"""Validate that the file has all required columns."""
	columns_set = {c.strip().lower() for c in columns}
	missing = REQUIRED_COLUMNS - columns_set
	if missing:
		frappe.throw(
			_("Missing required columns: {0}").format(", ".join(sorted(missing)))
		)
	unknown = columns_set - ALL_COLUMNS
	if unknown:
		frappe.throw(
			_("Unknown columns: {0}. Allowed columns: {1}").format(
				", ".join(sorted(unknown)),
				", ".join(sorted(ALL_COLUMNS)),
			)
		)


def validate_row(row, row_num):
	"""
	Validate a single row of import data.

	Args:
		row: dict with column names as keys
		row_num: 1-based row number for error reporting

	Returns:
		list of error strings (empty if valid)
	"""
	errors = []

	# Required fields presence
	for field in ("first_name", "last_name", "email", "batch_id", "enrolled_time", "expiry_time"):
		val = (row.get(field) or "").strip()
		if not val:
			errors.append(_("Row {0}: '{1}' is required").format(row_num, field))

	if errors:
		return errors

	# Name length
	if len(row["first_name"].strip()) < 2:
		errors.append(_("Row {0}: first_name must be at least 2 characters").format(row_num))
	if len(row["last_name"].strip()) < 2:
		errors.append(_("Row {0}: last_name must be at least 2 characters").format(row_num))

	# Email format
	email = row["email"].strip()
	if not EMAIL_REGEX.match(email):
		errors.append(_("Row {0}: Invalid email format '{1}'").format(row_num, email))

	# Batch existence
	batch_id = row["batch_id"].strip()
	if not frappe.db.exists("LMS Batch", batch_id):
		errors.append(_("Row {0}: Batch '{1}' does not exist").format(row_num, batch_id))

	# Date validation
	enrolled_time = _parse_date(row.get("enrolled_time", "").strip())
	expiry_time = _parse_date(row.get("expiry_time", "").strip())

	if enrolled_time is None:
		errors.append(_("Row {0}: Invalid enrolled_time date format").format(row_num))
	if expiry_time is None:
		errors.append(_("Row {0}: Invalid expiry_time date format").format(row_num))

	if enrolled_time and expiry_time and expiry_time <= enrolled_time:
		errors.append(
			_("Row {0}: expiry_time must be after enrolled_time").format(row_num)
		)

	return errors


def _parse_date(date_str):
	"""Try to parse a date string in common formats. Returns date or None."""
	if not date_str:
		return None
	for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
		try:
			return datetime.strptime(date_str, fmt).date()
		except ValueError:
			continue
	return None


def validate_file_size(file_doc):
	"""Validate that the uploaded file is within size limits."""
	if file_doc.file_size and file_doc.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
		frappe.throw(
			_("File size exceeds the maximum limit of {0}MB").format(MAX_FILE_SIZE_MB)
		)


def validate_file_extension(file_name):
	"""Validate that the file is CSV or Excel."""
	if not file_name:
		frappe.throw(_("No file provided"))
	ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
	if ext not in ("csv", "xlsx"):
		frappe.throw(_("Only CSV and Excel (.xlsx) files are supported"))
	return ext
