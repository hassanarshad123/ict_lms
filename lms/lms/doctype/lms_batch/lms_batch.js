// Copyright (c) 2022, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on("LMS Batch", {
	onload: function (frm) {
		frm.set_query("student", "students", function (doc) {
			return {
				filters: {
					ignore_user_type: 1,
				},
			};
		});

		frm.set_query("reference_doctype", "timetable", function () {
			let doctypes = ["Course Lesson", "LMS Quiz", "LMS Assignment"];
			return {
				filters: {
					name: ["in", doctypes],
				},
			};
		});

		frm.set_query("assessment_type", "assessment", function () {
			let doctypes = ["LMS Quiz", "LMS Assignment"];
			return {
				filters: {
					name: ["in", doctypes],
				},
			};
		});

		frm.set_query("reference_doctype", "timetable_legends", function () {
			let doctypes = ["Course Lesson", "LMS Quiz", "LMS Assignment"];
			return {
				filters: {
					name: ["in", doctypes],
				},
			};
		});

		if (frm.doc.timetable.length && !frm.doc.timetable_legends.length) {
			set_default_legends(frm);
		}
	},

	timetable_template: function (frm) {
		set_timetable(frm);
	},

	refresh: (frm) => {
		frm.add_web_link(
			`/lms/batches/details/${frm.doc.name}`,
			"See on website"
		);

		if (
			frappe.user_roles.includes("Moderator") ||
			frappe.user_roles.includes("Course Creator") ||
			frappe.user_roles.includes("System Manager")
		) {
			frm.add_custom_button(__("Bulk Import Students"), function () {
				show_bulk_import_dialog(frm);
			});
		}
	},
});

const set_timetable = (frm) => {
	if (frm.doc.timetable_template) {
		frm.clear_table("timetable");
		frm.refresh_fields();

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "LMS Batch Timetable",
				parent: "LMS Timetable Template",
				fields: [
					"reference_doctype",
					"reference_docname",
					"day",
					"start_time",
					"end_time",
					"duration",
					"milestone",
				],
				filters: {
					parent: frm.doc.timetable_template,
					parenttype: "LMS Timetable Template",
				},
				order_by: "idx",
			},
			callback: (data) => {
				add_timetable_rows(frm, data.message);
			},
		});
	}
};

const add_timetable_rows = (frm, timetable) => {
	timetable.forEach((row) => {
		let child = frm.add_child("timetable");
		child.reference_doctype = row.reference_doctype;
		child.reference_docname = row.reference_docname;
		child.date = frappe.datetime.add_days(frm.doc.start_date, row.day - 1);
		child.start_time = row.start_time;
		child.end_time = row.end_time
			? row.end_time
			: row.duration
			? moment
					.utc(row.start_time, "HH:mm")
					.add(row.duration, "hour")
					.format("HH:mm")
			: null;
		child.duration = row.duration;
		child.milestone = row.milestone;
	});
	frm.refresh_field("timetable");

	set_legends(frm);
};

const set_legends = (frm) => {
	if (frm.doc.timetable_template) {
		frm.clear_table("timetable_legends");
		frm.refresh_fields();
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "LMS Timetable Legend",
				parent: "LMS Timetable Template",
				fields: ["reference_doctype", "label", "color"],
				filters: {
					parent: frm.doc.timetable_template,
					parenttype: "LMS Timetable Template",
				},
				order_by: "idx",
			},
			callback: (data) => {
				add_legend_rows(frm, data.message);
			},
		});
	}
};

const add_legend_rows = (frm, legends) => {
	legends.forEach((row) => {
		let child = frm.add_child("timetable_legends");
		child.reference_doctype = row.reference_doctype;
		child.label = row.label;
		child.color = row.color;
	});
	frm.refresh_field("timetable_legends");
	frm.save();
};

const set_default_legends = (frm) => {
	const data = [
		{
			reference_doctype: "Course Lesson",
			label: "Lesson",
			color: "#449CF0",
		},
		{
			reference_doctype: "LMS Quiz",
			label: "LMS Quiz",
			color: "#39E4A5",
		},
		{
			reference_doctype: "LMS Assignment",
			label: "LMS Assignment",
			color: "#ECAD4B",
		},
		{
			reference_doctype: "LMS Live Class",
			label: "LMS Live Class",
			color: "#bb8be8",
		},
	];

	data.forEach((detail) => {
		let child = frm.add_child("timetable_legends");
		child.reference_doctype = detail.reference_doctype;
		child.label = detail.label;
		child.color = detail.color;
	});
	frm.refresh_field("timetable_legends");
	frm.save();
};

const show_bulk_import_dialog = (frm) => {
	let d = new frappe.ui.Dialog({
		title: __("Bulk Import Students"),
		fields: [
			{
				label: __("Upload CSV/Excel File"),
				fieldname: "file",
				fieldtype: "Attach",
				reqd: 1,
				description: __(
					"Upload a CSV or Excel (.xlsx) file with columns: first_name, last_name, email, phone, batch_id, enrolled_time, expiry_time"
				),
			},
			{
				label: __("Send Welcome Email"),
				fieldname: "send_welcome_email",
				fieldtype: "Check",
				default: 1,
				description: __(
					"Send login credentials to newly created users via email"
				),
			},
			{
				label: __("Duplicate Handling"),
				fieldname: "duplicate_action",
				fieldtype: "Select",
				options: "skip\nenroll_only",
				default: "skip",
				description: __(
					"'skip' = skip existing users, 'enroll_only' = enroll existing users without recreating"
				),
			},
			{
				fieldtype: "HTML",
				fieldname: "template_link",
				options:
					'<a href="#" class="download-template-link">' +
					__("Download CSV Template") +
					"</a>",
			},
		],
		primary_action_label: __("Import"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "lms.lms.api.bulk_import_users_with_enrollment",
				args: {
					file_url: values.file,
					send_welcome_email: values.send_welcome_email,
					duplicate_action: values.duplicate_action,
				},
				freeze: true,
				freeze_message: __("Importing users and creating enrollments..."),
				callback: function (r) {
					if (r.message && r.message.success) {
						show_import_results(r.message);
						frm.reload_doc();
					}
				},
				error: function () {
					frappe.msgprint(
						__("Import failed. Please check the file format and try again.")
					);
				},
			});
		},
	});

	// Bind download template link
	d.$wrapper.find(".download-template-link").on("click", function (e) {
		e.preventDefault();
		window.open(
			"/api/method/lms.lms.api.download_bulk_import_template",
			"_blank"
		);
	});

	d.show();
};

const show_import_results = (result) => {
	let summary = result.summary;
	let details = result.details;

	let msg = `
		<h5>${__("Import Summary")}</h5>
		<table class="table table-bordered">
			<tr><td><b>${__("Total Rows")}</b></td><td>${summary.total_rows}</td></tr>
			<tr><td><b>${__("Users Created")}</b></td><td>${summary.users_created}</td></tr>
			<tr><td><b>${__("Existing Users")}</b></td><td>${summary.users_existing}</td></tr>
			<tr><td><b>${__("Users Failed")}</b></td><td>${summary.users_failed}</td></tr>
			<tr><td><b>${__("Enrollments Created")}</b></td><td>${summary.enrollments_created}</td></tr>
			<tr><td><b>${__("Enrollments Failed")}</b></td><td>${summary.enrollments_failed}</td></tr>
		</table>
		<p>${__("Import Log ID")}: <b>${result.import_log_id}</b></p>
	`;

	if (details.failed && details.failed.length > 0) {
		msg += `<h5>${__("Failed Rows")}</h5><ul>`;
		details.failed.forEach((f) => {
			msg += `<li>${f.email || __("Unknown")} (Row ${f.row}): ${f.reason}</li>`;
		});
		msg += "</ul>";
	}

	if (details.created && details.created.length > 0) {
		msg += `<h5>${__("Created Users & Passwords")}</h5>`;
		msg += `<table class="table table-bordered table-sm">
			<thead><tr><th>${__("Email")}</th><th>${__("Batch")}</th><th>${__("Password")}</th></tr></thead><tbody>`;
		details.created.forEach((c) => {
			msg += `<tr><td>${c.email}</td><td>${c.batch}</td><td>${c.password}</td></tr>`;
		});
		msg += "</tbody></table>";
	}

	frappe.msgprint({
		title: __("Bulk Import Results"),
		indicator: summary.users_failed > 0 ? "orange" : "green",
		message: msg,
	});
};
