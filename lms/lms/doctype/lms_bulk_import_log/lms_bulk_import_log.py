import json

import frappe
from frappe.model.document import Document


class LMSBulkImportLog(Document):
	def before_save(self):
		self.generate_summary_html()

	def generate_summary_html(self):
		"""Generate a nice HTML summary of the import results."""
		if self.status == "Pending":
			self.summary_html = """
				<div style="padding: 15px; background: #f0f4f7; border-radius: 8px; text-align: center;">
					<p style="margin: 0; color: #6c7680;">Import is pending...</p>
				</div>
			"""
			return

		if self.status == "Processing":
			self.summary_html = f"""
				<div style="padding: 15px; background: #fff3cd; border-radius: 8px; text-align: center;">
					<p style="margin: 0; color: #856404; font-weight: 500;">
						⏳ Processing... {self.users_created or 0} users created so far
					</p>
				</div>
			"""
			return

		if self.status == "Failed":
			self.summary_html = f"""
				<div style="padding: 15px; background: #f8d7da; border-radius: 8px;">
					<p style="margin: 0; color: #721c24; font-weight: 500;">❌ Import Failed</p>
					<p style="margin: 10px 0 0 0; color: #721c24; font-size: 12px;">{self.error_log or 'Unknown error'}</p>
				</div>
			"""
			return

		# Completed status - show detailed summary
		users_created = self.users_created or 0
		users_enrolled_existing = self.users_enrolled_existing or 0
		users_skipped = self.users_skipped or 0
		users_failed = self.users_failed or 0
		enrollments_created = self.enrollments_created or 0
		total_rows = self.total_rows or 0

		# Parse failed details from JSON
		failed_list = []
		if self.details_json:
			try:
				details = json.loads(self.details_json)
				failed_list = details.get("failed", [])
			except (json.JSONDecodeError, TypeError):
				pass

		# Build HTML
		html_parts = [
			'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif;">',
			# Success banner
			'<div style="padding: 15px; background: #d4edda; border-radius: 8px; margin-bottom: 15px;">',
			f'<p style="margin: 0; color: #155724; font-weight: 600; font-size: 16px;">✅ Import Completed</p>',
			f'<p style="margin: 5px 0 0 0; color: #155724;">Processed {total_rows} rows</p>',
			'</div>',
			# Stats grid
			'<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 15px;">',
		]

		# Stat cards
		stats = [
			("🆕 New Users", users_created, "#28a745"),
			("👥 Existing Enrolled", users_enrolled_existing, "#17a2b8"),
			("⏭️ Skipped", users_skipped, "#6c757d"),
			("❌ Failed", users_failed, "#dc3545"),
			("📝 Enrollments", enrollments_created, "#007bff"),
		]

		for label, value, color in stats:
			html_parts.append(f'''
				<div style="padding: 12px; background: #f8f9fa; border-radius: 6px; text-align: center; border-left: 4px solid {color};">
					<div style="font-size: 24px; font-weight: 600; color: {color};">{value}</div>
					<div style="font-size: 12px; color: #6c7680; margin-top: 4px;">{label}</div>
				</div>
			''')

		html_parts.append('</div>')

		# Failed rows list (if any)
		if failed_list:
			html_parts.append('<div style="margin-top: 15px;">')
			html_parts.append('<p style="font-weight: 600; color: #dc3545; margin-bottom: 10px;">Failed Rows:</p>')
			html_parts.append('<div style="max-height: 200px; overflow-y: auto; background: #fff5f5; border-radius: 6px; padding: 10px;">')
			for item in failed_list[:20]:  # Show max 20 failures
				email = item.get("email", "Unknown")
				reason = item.get("reason", "Unknown error")
				row = item.get("row", "?")
				html_parts.append(f'''
					<div style="padding: 8px; border-bottom: 1px solid #f8d7da; font-size: 13px;">
						<span style="color: #721c24;">Row {row}:</span>
						<span style="color: #495057;">{email}</span>
						<span style="color: #dc3545;"> - {reason}</span>
					</div>
				''')
			if len(failed_list) > 20:
				html_parts.append(f'<div style="padding: 8px; color: #6c7680; font-style: italic;">...and {len(failed_list) - 20} more</div>')
			html_parts.append('</div></div>')

		html_parts.append('</div>')
		self.summary_html = "".join(html_parts)
