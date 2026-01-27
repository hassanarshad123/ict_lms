import csv
import io

import frappe
from frappe import _

from lms.lms.bulk_import.validators import (
	MAX_ROWS,
	_parse_date,
	validate_columns,
	validate_file_extension,
	validate_file_size,
	validate_row,
)


def parse_import_file(file_url):
	"""
	Parse a CSV or Excel file uploaded via Frappe File Manager.

	Args:
		file_url: URL of the uploaded file (e.g. /files/import.csv)

	Returns:
		tuple: (rows, errors)
			rows - list of dicts with normalized column names
			errors - list of validation error strings
	"""
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if not file_doc:
		frappe.throw(_("File not found: {0}").format(file_url))

	validate_file_size(file_doc)
	ext = validate_file_extension(file_doc.file_name)

	file_content = file_doc.get_content()

	if ext == "csv":
		rows = _parse_csv(file_content)
	else:
		rows = _parse_xlsx(file_content)

	if not rows:
		frappe.throw(_("The file is empty or has no data rows"))

	if len(rows) > MAX_ROWS:
		frappe.throw(
			_("File contains {0} rows. Maximum allowed is {1}").format(len(rows), MAX_ROWS)
		)

	# Validate all rows
	all_errors = []
	valid_rows = []
	for idx, row in enumerate(rows):
		row_errors = validate_row(row, idx + 1)
		if row_errors:
			all_errors.extend(row_errors)
		else:
			# Normalize and enrich
			row["first_name"] = row["first_name"].strip()
			row["last_name"] = row["last_name"].strip()
			row["email"] = row["email"].strip().lower()
			row["batch_id"] = row["batch_id"].strip()
			row["enrolled_time"] = _parse_date(row["enrolled_time"].strip()).strftime("%Y-%m-%d")
			row["expiry_time"] = _parse_date(row["expiry_time"].strip()).strftime("%Y-%m-%d")
			row["phone"] = (row.get("phone") or "").strip()
			row["password"] = generate_password(row["last_name"], row["batch_id"])
			valid_rows.append(row)

	return valid_rows, all_errors


def _parse_csv(content):
	"""Parse CSV file content into list of dicts."""
	if isinstance(content, bytes):
		content = content.decode("utf-8-sig")

	reader = csv.DictReader(io.StringIO(content))
	if reader.fieldnames:
		# Normalize column names to lowercase
		reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
		validate_columns(reader.fieldnames)

	rows = []
	for row in reader:
		# Normalize keys
		normalized = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
		rows.append(normalized)
	return rows


def _parse_xlsx(content):
	"""Parse Excel (.xlsx) file content into list of dicts."""
	try:
		import openpyxl
	except ImportError:
		frappe.throw(
			_("openpyxl is required to parse Excel files. Please install it: pip install openpyxl")
		)

	if isinstance(content, str):
		content = content.encode("utf-8")

	wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	ws = wb.active

	rows_iter = ws.iter_rows(values_only=True)
	try:
		header = next(rows_iter)
	except StopIteration:
		return []

	columns = [str(c).strip().lower() if c else "" for c in header]
	validate_columns(columns)

	rows = []
	for row_values in rows_iter:
		if all(v is None for v in row_values):
			continue
		row = {}
		for col_name, value in zip(columns, row_values):
			row[col_name] = str(value).strip() if value is not None else ""
		rows.append(row)

	wb.close()
	return rows


def generate_password(last_name, batch_id):
	"""
	Generate password from last name and batch ID.

	Rule: First 2 letters of last name (lowercase) + batch numeric part
	Examples:
		Ahmed + BATCH-18434 → ah18434
		Khan + BATCH-001 → kh001
	"""
	prefix = last_name[:2].lower()
	# Extract the part after the last hyphen, or use the full batch_id if no hyphen
	batch_suffix = batch_id.split("-")[-1] if "-" in batch_id else batch_id
	return prefix + batch_suffix
