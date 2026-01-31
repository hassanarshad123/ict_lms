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
	"""
	Try to parse a date string in all common formats. Returns date or None.

	Handles:
	- ISO formats: 2026-01-13, 2026/01/13
	- US formats: 01/13/2026, 1/13/2026
	- EU formats: 13/01/2026, 13-01-2026
	- With time: 2026-01-13 00:00:00, 2026-01-13T00:00:00Z
	- Month names: Jan 13, 2026, 13 January 2026
	- Excel serial dates: 46035 (days since 1900-01-01)
	"""
	if not date_str:
		return None

	# Strip whitespace
	date_str = str(date_str).strip()

	# Handle Excel serial date numbers (integer representing days since 1899-12-30)
	if date_str.isdigit():
		try:
			serial = int(date_str)
			# Excel serial dates are typically 5 digits for modern dates (e.g., 46035 = 2026-01-13)
			if 1 < serial < 100000:
				# Excel epoch is 1899-12-30 (accounting for the leap year bug)
				from datetime import timedelta
				excel_epoch = datetime(1899, 12, 30)
				return (excel_epoch + timedelta(days=serial)).date()
		except (ValueError, OverflowError):
			pass

	# Remove time portion if present (e.g., "2026-01-13 00:00:00" -> "2026-01-13")
	# Handle both space and T separators for datetime
	if " " in date_str:
		date_part = date_str.split(" ")[0]
		# Check if the part after space looks like time (contains :)
		if ":" in date_str.split(" ", 1)[1]:
			date_str = date_part
	if "T" in date_str:
		date_str = date_str.split("T")[0]

	# Normalize single-digit months/days by zero-padding (e.g., 1/30/2026 -> 01/30/2026)
	normalized = date_str
	if "/" in date_str:
		parts = date_str.split("/")
		if len(parts) == 3:
			parts = [p.zfill(2) if len(p) <= 2 else p for p in parts]
			normalized = "/".join(parts)
	elif "-" in date_str and not date_str.startswith("20"):
		parts = date_str.split("-")
		if len(parts) == 3:
			parts = [p.zfill(2) if len(p) <= 2 else p for p in parts]
			normalized = "-".join(parts)
	elif "." in date_str:
		parts = date_str.split(".")
		if len(parts) == 3:
			parts = [p.zfill(2) if len(p) <= 2 else p for p in parts]
			normalized = ".".join(parts)

	# Try all common date formats
	# NOTE: US format (M/D/Y) is tried BEFORE EU format (D/M/Y) because
	# ambiguous dates like 1/9/2026 are more commonly US format in this context
	formats = [
		# ISO and standard formats (unambiguous)
		"%Y-%m-%d",
		"%Y/%m/%d",
		"%Y.%m.%d",
		# Month first (common in US) - try BEFORE day-first to handle ambiguous dates
		"%m/%d/%Y",
		"%m-%d-%Y",
		"%m.%d.%Y",
		# Day first (common in UK, Europe)
		"%d/%m/%Y",
		"%d-%m-%Y",
		"%d.%m.%Y",
		# Two-digit year variants (US first)
		"%m/%d/%y",
		"%d/%m/%y",
		"%m-%d-%y",
		"%d-%m-%y",
		"%y-%m-%d",
		# Month name formats
		"%b %d, %Y",  # Jan 13, 2026
		"%B %d, %Y",  # January 13, 2026
		"%b %d %Y",  # Jan 13 2026
		"%B %d %Y",  # January 13 2026
		"%d %b %Y",  # 13 Jan 2026
		"%d %B %Y",  # 13 January 2026
		"%d-%b-%Y",  # 13-Jan-2026
		"%d-%B-%Y",  # 13-January-2026
		"%Y%m%d",  # 20260113 (compact)
	]

	for fmt in formats:
		try:
			return datetime.strptime(normalized, fmt).date()
		except ValueError:
			continue

	# Fallback: try dateutil parser (handles almost any format)
	try:
		from dateutil import parser as dateutil_parser
		parsed = dateutil_parser.parse(date_str, dayfirst=False)
		return parsed.date()
	except Exception:
		pass

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
