# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""
Background job handler for processing Zoom recordings and uploading to Vimeo.
"""

import os
import tempfile
import frappe
from frappe import _


def process_recording_upload(recording_name):
	"""
	Main background job for processing a recording upload.

	Flow:
	1. Fetch recording details from Zoom
	2. Download recording to temp file
	3. Upload to Vimeo with privacy settings
	4. Update recording document
	5. Clean up temp file
	"""
	recording = frappe.get_doc("LMS Course Recording", recording_name)

	try:
		# Update status to Processing
		recording.status = "Processing"
		recording.save(ignore_permissions=True)
		frappe.db.commit()

		# Step 1: Get Zoom recording download URL
		zoom_download_info = get_zoom_recording_download_url(recording)
		if not zoom_download_info:
			raise Exception("Could not fetch recording from Zoom")

		recording.zoom_recording_id = zoom_download_info.get("recording_id")
		recording.zoom_download_url = zoom_download_info.get("download_url")
		recording.duration = zoom_download_info.get("duration", 0)
		recording.save(ignore_permissions=True)
		frappe.db.commit()

		# Step 2: Download recording to temp file
		temp_file_path = download_zoom_recording(
			zoom_download_info.get("download_url"), recording.name
		)

		try:
			# Step 3: Upload to Vimeo
			vimeo_result = upload_to_vimeo(temp_file_path, recording)

			# Step 4: Update recording with Vimeo details
			recording.vimeo_video_id = vimeo_result.get("video_id")
			recording.vimeo_uri = vimeo_result.get("uri")
			recording.vimeo_player_embed_url = vimeo_result.get("player_embed_url")
			recording.vimeo_privacy_status = vimeo_result.get("privacy_status")
			recording.thumbnail = vimeo_result.get("thumbnail")
			recording.status = "Uploaded"
			recording.error_message = None
			recording.save(ignore_permissions=True)
			frappe.db.commit()

			frappe.publish_realtime(
				"recording_uploaded",
				{"recording": recording.name, "course": recording.course},
				doctype="LMS Course Recording",
			)

		finally:
			# Step 5: Clean up temp file
			if os.path.exists(temp_file_path):
				os.remove(temp_file_path)

	except Exception as e:
		frappe.log_error(
			f"Recording upload failed for {recording_name}: {str(e)}",
			"Recording Upload Error",
		)
		recording.reload()
		recording.status = "Failed"
		recording.error_message = str(e)[:500]  # Truncate to fit in field
		recording.save(ignore_permissions=True)
		frappe.db.commit()
		raise


def get_zoom_recording_download_url(recording):
	"""
	Fetch recording details and download URL from Zoom API.
	"""
	if not recording.zoom_meeting_uuid:
		return None

	live_class = frappe.get_doc("LMS Live Class", recording.live_class)
	batch = frappe.get_doc("LMS Batch", live_class.batch_name)

	if not batch.zoom_account:
		raise Exception("Batch has no Zoom account configured")

	# Authenticate with Zoom
	from lms.lms.doctype.lms_batch.lms_batch import authenticate

	access_token = authenticate(batch.zoom_account)

	import requests

	# Get recordings for the meeting
	# Double-encode the UUID as Zoom requires for certain UUIDs
	import urllib.parse

	meeting_uuid = recording.zoom_meeting_uuid
	if meeting_uuid.startswith("/") or "//" in meeting_uuid:
		meeting_uuid = urllib.parse.quote(urllib.parse.quote(meeting_uuid, safe=""), safe="")

	response = requests.get(
		f"https://api.zoom.us/v2/past_meetings/{meeting_uuid}/recordings",
		headers={
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json",
		},
		timeout=30,
	)

	if response.status_code != 200:
		error_msg = response.json().get("message", "Unknown error")
		if response.status_code == 404:
			# Recording not ready yet or doesn't exist
			return None
		raise Exception(f"Zoom API error: {error_msg}")

	data = response.json()
	recording_files = data.get("recording_files", [])

	# Find the main video recording (MP4)
	for file in recording_files:
		if file.get("file_type") == "MP4" and file.get("recording_type") in [
			"shared_screen_with_speaker_view",
			"shared_screen_with_gallery_view",
			"speaker_view",
			"gallery_view",
			"active_speaker",
		]:
			return {
				"recording_id": file.get("id"),
				"download_url": file.get("download_url"),
				"duration": int(data.get("duration", 0)) * 60,  # Convert minutes to seconds
			}

	# Fallback to any MP4
	for file in recording_files:
		if file.get("file_type") == "MP4":
			return {
				"recording_id": file.get("id"),
				"download_url": file.get("download_url"),
				"duration": int(data.get("duration", 0)) * 60,
			}

	return None


def download_zoom_recording(download_url, recording_name):
	"""
	Download Zoom recording to a temporary file.
	Returns the path to the temp file.
	"""
	import requests

	# Get Zoom access token for download
	# Zoom download URLs require authentication
	# The download_url includes a token parameter from the API response

	temp_dir = tempfile.gettempdir()
	temp_file_path = os.path.join(temp_dir, f"recording_{recording_name}.mp4")

	response = requests.get(download_url, stream=True, timeout=60)
	response.raise_for_status()

	total_size = int(response.headers.get("content-length", 0))
	downloaded = 0

	with open(temp_file_path, "wb") as f:
		for chunk in response.iter_content(chunk_size=8192):
			if chunk:
				f.write(chunk)
				downloaded += len(chunk)

	if downloaded == 0:
		raise Exception("Downloaded file is empty")

	return temp_file_path


def upload_to_vimeo(file_path, recording):
	"""
	Upload video file to Vimeo with privacy settings.
	Returns dict with Vimeo video details.
	"""
	settings = frappe.get_single("LMS Vimeo Settings")

	if not settings.enabled:
		raise Exception("Vimeo integration is not enabled")

	access_token = settings.get_password("access_token")
	file_size = os.path.getsize(file_path)

	import requests

	headers = {
		"Authorization": f"Bearer {access_token}",
		"Accept": "application/vnd.vimeo.*+json;version=3.4",
		"Content-Type": "application/json",
	}

	# Step 1: Create video placeholder with TUS upload approach
	create_payload = {
		"upload": {
			"approach": "tus",
			"size": str(file_size),
		},
		"name": recording.title,
		"description": f"Recording from {recording.recorded_on} - {recording.course}",
		"privacy": {
			"view": "disable",  # Not publicly discoverable
			"embed": "whitelist",  # Only whitelisted domains
			"download": False,
			"add": False,
			"comments": "nobody",
		},
	}

	# Add to folder if configured
	if settings.default_folder:
		create_payload["folder_uri"] = f"/me/folders/{settings.default_folder}"

	response = requests.post(
		"https://api.vimeo.com/me/videos",
		headers=headers,
		json=create_payload,
		timeout=60,
	)

	if response.status_code not in [200, 201]:
		error = response.json().get("error", "Unknown error")
		raise Exception(f"Failed to create Vimeo video: {error}")

	video_data = response.json()
	upload_link = video_data.get("upload", {}).get("upload_link")
	video_uri = video_data.get("uri")
	video_id = video_uri.split("/")[-1] if video_uri else None

	if not upload_link:
		raise Exception("No upload link received from Vimeo")

	# Step 2: Upload file using TUS protocol
	upload_video_tus(file_path, upload_link, file_size)

	# Step 3: Set embed domain whitelist
	embed_domains = settings.embed_whitelist.split(",")
	for domain in embed_domains:
		domain = domain.strip()
		if domain:
			try:
				requests.put(
					f"https://api.vimeo.com{video_uri}/privacy/domains/{domain}",
					headers=headers,
					timeout=30,
				)
			except Exception as e:
				frappe.log_error(
					f"Failed to add domain {domain} to whitelist: {str(e)}",
					"Vimeo Domain Whitelist Error",
				)

	# Step 4: Get video details including embed URL and thumbnail
	video_response = requests.get(
		f"https://api.vimeo.com{video_uri}",
		headers=headers,
		timeout=30,
	)

	if video_response.status_code == 200:
		video_details = video_response.json()
		player_embed_url = video_details.get("player_embed_url")
		pictures = video_details.get("pictures", {}).get("sizes", [])
		thumbnail = pictures[-1].get("link") if pictures else None
		privacy_status = video_details.get("privacy", {}).get("view", "unknown")
	else:
		player_embed_url = f"https://player.vimeo.com/video/{video_id}"
		thumbnail = None
		privacy_status = "unknown"

	return {
		"video_id": video_id,
		"uri": video_uri,
		"player_embed_url": player_embed_url,
		"thumbnail": thumbnail,
		"privacy_status": privacy_status,
	}


def upload_video_tus(file_path, upload_link, file_size):
	"""
	Upload video using TUS resumable upload protocol.
	"""
	import requests

	chunk_size = 128 * 1024 * 1024  # 128MB chunks
	offset = 0

	with open(file_path, "rb") as f:
		while offset < file_size:
			chunk = f.read(chunk_size)
			chunk_length = len(chunk)

			headers = {
				"Tus-Resumable": "1.0.0",
				"Upload-Offset": str(offset),
				"Content-Type": "application/offset+octet-stream",
				"Content-Length": str(chunk_length),
			}

			response = requests.patch(
				upload_link, headers=headers, data=chunk, timeout=600
			)

			if response.status_code not in [200, 204]:
				raise Exception(f"TUS upload failed at offset {offset}: {response.text}")

			offset += chunk_length

	# Verify upload is complete
	head_response = requests.head(
		upload_link, headers={"Tus-Resumable": "1.0.0"}, timeout=30
	)

	if head_response.status_code == 200:
		upload_offset = int(head_response.headers.get("Upload-Offset", 0))
		if upload_offset != file_size:
			raise Exception(
				f"Upload incomplete: {upload_offset} of {file_size} bytes uploaded"
			)
