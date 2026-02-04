# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

"""
Vimeo recording processor for the native Vimeo-Zoom integration.

This module handles:
1. Fetching video details from Vimeo API
2. Parsing video title to extract meeting topic and datetime
3. Matching the video to the correct LMS Live Class
4. Creating LMS Course Recording with Vimeo details
5. Applying privacy settings to the video
"""

import json
import re
import time as time_module
import frappe
import requests
from frappe import _
from frappe.utils import getdate, get_time, cint
from datetime import datetime, timedelta


def process_vimeo_recording(video_id, video_uri=None, timestamp=None):
    """
    Main entry point for processing a Vimeo recording.

    Called as a background job when Vimeo webhook fires.

    Args:
        video_id: The Vimeo video ID
        video_uri: The full video URI (e.g., /videos/123456789)
        timestamp: Webhook timestamp
    """
    frappe.logger().info(f"Processing Vimeo recording: {video_id}")

    try:
        # 1. Check if recording already exists
        existing = frappe.db.exists(
            "LMS Course Recording", {"vimeo_video_id": video_id}
        )
        if existing:
            frappe.logger().info(f"Recording already exists for video {video_id}: {existing}")
            return existing

        # 2. Fetch video details from Vimeo
        video_data = fetch_vimeo_video(video_id)
        if not video_data:
            frappe.log_error(
                f"Failed to fetch video details from Vimeo for video {video_id}",
                "Vimeo Processor Error"
            )
            return None

        # 3. Parse the video title to extract meeting topic and datetime
        title = video_data.get("name", "")
        parsed = parse_vimeo_title(title)

        if not parsed:
            frappe.logger().warning(f"Could not parse Vimeo title: {title}")
            # Create orphan recording (no live class match)
            return create_orphan_recording(video_id, video_data)

        meeting_topic, recording_date, recording_time = parsed

        # 4. Find matching LMS Live Class
        live_class = find_live_class(meeting_topic, recording_date, recording_time)

        if not live_class:
            frappe.logger().warning(
                f"No live class match for: topic='{meeting_topic}', date={recording_date}"
            )
            # Create orphan recording
            return create_orphan_recording(video_id, video_data)

        # 5. Check for existing recording for this live class
        existing_for_class = frappe.db.exists(
            "LMS Course Recording", {"live_class": live_class.name}
        )
        if existing_for_class:
            frappe.logger().info(
                f"Recording already exists for live class {live_class.name}: {existing_for_class}"
            )
            return existing_for_class

        # 6. Create recording linked to live class
        recording_name = create_recording(video_id, video_data, live_class)

        # 7. Apply privacy settings
        apply_vimeo_privacy(video_id)

        # 8. Publish realtime event
        frappe.publish_realtime(
            "recording_uploaded",
            {"recording": recording_name, "course": live_class.course},
            after_commit=True,
        )

        frappe.logger().info(f"Successfully processed recording: {recording_name}")
        return recording_name

    except Exception as e:
        frappe.log_error(
            f"Error processing Vimeo recording {video_id}: {str(e)}",
            "Vimeo Processor Error"
        )
        raise


def fetch_vimeo_video(video_id):
    """
    Fetch video details from Vimeo API.

    Returns dict with video metadata or None if failed.
    """
    settings = frappe.get_single("LMS Vimeo Settings")
    access_token = settings.get_password("access_token")

    if not access_token:
        frappe.throw(_("Vimeo access token not configured"))

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.vimeo.*+json;version=3.4",
    }

    try:
        response = requests.get(
            f"https://api.vimeo.com/videos/{video_id}",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            return response.json()
        else:
            frappe.log_error(
                f"Vimeo API error {response.status_code}: {response.text}",
                "Vimeo API Error"
            )
            return None

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            f"Vimeo API request failed: {str(e)}",
            "Vimeo API Error"
        )
        return None


def parse_vimeo_title(title):
    """
    Parse Vimeo video title to extract meeting topic and datetime.

    Vimeo titles from Zoom integration follow the format:
    "{Meeting Topic} {YYYY-MM-DD} {HH:MM:SS}"

    Example: "Introduction to Python 2026-01-10 19:14:35"

    Returns:
        tuple: (topic, date, time) or None if parsing fails
    """
    if not title:
        return None

    # Pattern: anything followed by date and time at the end
    # Date format: YYYY-MM-DD
    # Time format: HH:MM:SS
    pattern = r'^(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})$'
    match = re.match(pattern, title.strip())

    if match:
        topic = match.group(1).strip()
        date_str = match.group(2)
        time_str = match.group(3)

        try:
            # Validate date and time
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            parsed_time = datetime.strptime(time_str, "%H:%M:%S").time()
            return (topic, parsed_date, parsed_time)
        except ValueError:
            return None

    return None


def find_live_class(topic, recording_date, recording_time):
    """
    Find the LMS Live Class that matches the recording.

    Matching strategy:
    1. Exact title match + exact date
    2. Title contains topic + exact date
    3. Exact title match + date within 1 day (for timezone edge cases)

    Args:
        topic: The meeting topic from video title
        recording_date: Date from video title
        recording_time: Time from video title

    Returns:
        dict with live class details or None
    """
    frappe.logger().info(f"find_live_class: topic='{topic}', date={recording_date}, time={recording_time}")

    # Strategy 1: Exact title match + exact date
    live_class = frappe.db.get_value(
        "LMS Live Class",
        {"title": topic, "date": recording_date},
        ["name", "batch_name", "host", "title", "date", "time", "uuid"],
        as_dict=True,
    )

    if live_class:
        frappe.logger().info(f"find_live_class: Found exact match: {live_class.name}")
        # Get course from batch
        live_class["course"] = get_course_from_batch(live_class.batch_name)
        if not live_class["course"]:
            frappe.logger().warning(f"find_live_class: No course found for batch {live_class.batch_name}")
        return live_class

    # Strategy 2: Title contains topic + exact date
    # (handles cases where Zoom topic might be slightly different)
    all_classes_on_date = frappe.get_all(
        "LMS Live Class",
        filters={"date": recording_date},
        fields=["name", "batch_name", "host", "title", "date", "time", "uuid"],
    )
    frappe.logger().info(f"find_live_class: Found {len(all_classes_on_date)} classes on {recording_date}")

    for lc in all_classes_on_date:
        # Check if the live class title is contained in the topic or vice versa
        if topic.lower() in lc.title.lower() or lc.title.lower() in topic.lower():
            frappe.logger().info(f"find_live_class: Found partial match: {lc.name} (title='{lc.title}')")
            lc["course"] = get_course_from_batch(lc.batch_name)
            if not lc["course"]:
                frappe.logger().warning(f"find_live_class: No course found for batch {lc.batch_name}")
            return lc

    # Strategy 3: Exact title + date within 1 day (timezone edge cases)
    date_before = recording_date - timedelta(days=1)
    date_after = recording_date + timedelta(days=1)
    frappe.logger().info(f"find_live_class: Trying date range {date_before} to {date_after}")

    live_class = frappe.db.get_value(
        "LMS Live Class",
        {
            "title": topic,
            "date": ["between", [date_before, date_after]],
        },
        ["name", "batch_name", "host", "title", "date", "time", "uuid"],
        as_dict=True,
    )

    if live_class:
        frappe.logger().info(f"find_live_class: Found date-range match: {live_class.name}")
        live_class["course"] = get_course_from_batch(live_class.batch_name)
        if not live_class["course"]:
            frappe.logger().warning(f"find_live_class: No course found for batch {live_class.batch_name}")
        return live_class

    frappe.logger().warning(f"find_live_class: No matching live class found for topic='{topic}', date={recording_date}")
    return None


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


def create_recording(video_id, video_data, live_class):
    """
    Create LMS Course Recording document linked to a live class.
    """
    # Extract video details
    duration = video_data.get("duration", 0)  # seconds
    embed_data = video_data.get("embed", {})
    pictures = video_data.get("pictures", {})

    # Get embed URL
    embed_html = embed_data.get("html", "")
    embed_url = extract_embed_url(embed_html) or f"https://player.vimeo.com/video/{video_id}"

    # Get thumbnail
    thumbnail_url = get_best_thumbnail(pictures)

    # Set status to "Uploaded" - the video is on Vimeo and will be playable
    # The hourly check_processing_recordings job can verify if still processing
    status = "Uploaded"

    # Create recording
    recording = frappe.new_doc("LMS Course Recording")
    recording.title = live_class.title
    recording.course = live_class.course
    recording.live_class = live_class.name
    recording.batch = live_class.batch_name
    recording.recorded_on = live_class.date
    recording.instructor = live_class.host
    recording.duration = duration
    recording.status = status

    # Vimeo details
    recording.vimeo_video_id = video_id
    recording.vimeo_uri = f"/videos/{video_id}"
    recording.vimeo_player_embed_url = embed_url
    recording.vimeo_privacy_status = video_data.get("privacy", {}).get("view", "unknown")

    # Zoom details (from live class if available)
    if live_class.get("uuid"):
        recording.zoom_meeting_uuid = live_class.uuid

    # Thumbnail - download and attach if available
    if thumbnail_url:
        try:
            recording.thumbnail = download_thumbnail(thumbnail_url, video_id)
        except Exception:
            pass  # Non-critical, skip thumbnail

    recording.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().info(f"Created recording document: {recording.name}")

    # Create lesson for this recording
    if live_class.course:
        frappe.logger().info(f"Attempting to create lesson for recording {recording.name} in course {live_class.course}")
        try:
            lesson_name = create_lesson_for_recording(
                course=live_class.course,
                title=live_class.title,
                vimeo_embed_url=embed_url
            )
            if lesson_name:
                frappe.logger().info(f"Created lesson {lesson_name} for recording {recording.name}")
            else:
                frappe.logger().warning(f"create_lesson_for_recording returned None for recording {recording.name}")
        except Exception as e:
            # Log error but don't fail the recording creation
            frappe.log_error(
                f"Failed to create lesson for recording {recording.name}: {str(e)}\n{frappe.get_traceback()}",
                "Recording Lesson Error"
            )
    else:
        frappe.logger().warning(f"No course linked to recording {recording.name} - skipping lesson creation")

    return recording.name


def create_lesson_for_recording(course, title, vimeo_embed_url):
    """
    Create a lesson for the recording in a "Recordings" chapter.

    1. Find or create "Recordings" chapter in the course
    2. Add chapter to course's chapters table (if new)
    3. Create lesson with Vimeo embed
    4. Add lesson to chapter's lessons table

    Args:
        course: The course name to add the lesson to
        title: The live class title (used to name the lesson)
        vimeo_embed_url: The Vimeo player embed URL

    Returns:
        The lesson name if created, None otherwise
    """
    frappe.logger().info(f"create_lesson_for_recording called: course={course}, title={title}, url={vimeo_embed_url}")

    if not course or not vimeo_embed_url:
        frappe.logger().warning(f"create_lesson_for_recording: Missing course ({course}) or embed_url ({vimeo_embed_url})")
        return None

    RECORDINGS_CHAPTER_TITLE = "Recordings"
    lesson_title = f"{title} Recording"

    # Check if lesson already exists (avoid duplicates)
    # Note: We search by title only since course is a fetch_from field
    existing_lesson = frappe.db.get_value(
        "Course Lesson",
        {"title": lesson_title},
        ["name", "chapter"],
        as_dict=True
    )
    if existing_lesson:
        # Verify it's for the same course by checking the chapter
        existing_chapter_course = frappe.db.get_value("Course Chapter", existing_lesson.chapter, "course")
        if existing_chapter_course == course:
            frappe.logger().info(f"Lesson already exists: {existing_lesson.name}")
            return existing_lesson.name
        # Different course, proceed to create new lesson

    # Find existing "Recordings" chapter for this course
    chapter_name = frappe.db.get_value(
        "Course Chapter",
        {"course": course, "title": RECORDINGS_CHAPTER_TITLE},
        "name"
    )
    frappe.logger().info(f"Looking for Recordings chapter in course {course}: found={chapter_name}")

    # Create chapter if not exists
    if not chapter_name:
        frappe.logger().info(f"Creating new Recordings chapter for course {course}")
        try:
            chapter_doc = frappe.new_doc("Course Chapter")
            chapter_doc.title = RECORDINGS_CHAPTER_TITLE
            chapter_doc.course = course
            chapter_doc.insert(ignore_permissions=True)
            frappe.db.commit()  # Commit immediately after chapter creation
            chapter_name = chapter_doc.name
            frappe.logger().info(f"Created Recordings chapter: {chapter_name}")
        except Exception as e:
            frappe.log_error(
                f"Failed to create Recordings chapter for course {course}: {str(e)}\n{frappe.get_traceback()}",
                "Recording Chapter Creation Error"
            )
            return None

    # Always ensure the chapter is in the course's chapters table (Chapter Reference)
    # This is required for the chapter to appear in course outline
    # Check if already linked to prevent duplicates
    try:
        chapter_already_linked = frappe.db.exists(
            "Chapter Reference",
            {"parent": course, "chapter": chapter_name}
        )
        frappe.logger().info(f"Chapter {chapter_name} already linked to course {course}: {chapter_already_linked}")

        if not chapter_already_linked:
            # Directly insert Chapter Reference to bypass LMS Course permission checks
            # Get the next idx for ordering
            max_idx = frappe.db.sql("""
                SELECT COALESCE(MAX(idx), 0) FROM `tabChapter Reference`
                WHERE parent = %s
            """, (course,))[0][0]

            frappe.get_doc({
                "doctype": "Chapter Reference",
                "parent": course,
                "parenttype": "LMS Course",
                "parentfield": "chapters",
                "chapter": chapter_name,
                "idx": max_idx + 1
            }).insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info(f"Added chapter {chapter_name} to course {course} (idx={max_idx + 1})")
    except Exception as e:
        frappe.log_error(
            f"Failed to link chapter {chapter_name} to course {course}: {str(e)}\n{frappe.get_traceback()}",
            "Recording Chapter Link Error"
        )
        # Continue anyway - the chapter exists, just not linked to course outline
        # The lesson can still be created

    # Create the lesson with Vimeo embed using EditorJS JSON format
    # This is the same format the frontend uses when saving lessons
    editor_content = {
        "time": int(time_module.time() * 1000),
        "blocks": [
            {
                "type": "embed",
                "data": {
                    "service": "vimeo",
                    "embed": vimeo_embed_url
                }
            }
        ],
        "version": "2.28.2"
    }

    frappe.logger().info(f"Creating lesson: title='{lesson_title}', chapter={chapter_name}")
    try:
        lesson = frappe.new_doc("Course Lesson")
        lesson.title = lesson_title
        lesson.chapter = chapter_name
        # Use content field with EditorJS JSON format (same as frontend)
        lesson.content = json.dumps(editor_content)
        lesson.insert(ignore_permissions=True)
        frappe.db.commit()  # Commit after lesson creation
        frappe.logger().info(f"Created lesson document: {lesson.name}")
    except Exception as e:
        frappe.log_error(
            f"Failed to create lesson '{lesson_title}' in chapter {chapter_name}: {str(e)}\n{frappe.get_traceback()}",
            "Recording Lesson Creation Error"
        )
        return None

    # Add lesson to chapter's lessons table (Lesson Reference)
    try:
        # Check if lesson is already linked to chapter
        lesson_already_linked = frappe.db.exists(
            "Lesson Reference",
            {"parent": chapter_name, "lesson": lesson.name}
        )

        if not lesson_already_linked:
            # Get the next idx for ordering
            max_idx = frappe.db.sql("""
                SELECT COALESCE(MAX(idx), 0) FROM `tabLesson Reference`
                WHERE parent = %s
            """, (chapter_name,))[0][0]

            # Directly insert Lesson Reference to avoid any permission issues
            frappe.get_doc({
                "doctype": "Lesson Reference",
                "parent": chapter_name,
                "parenttype": "Course Chapter",
                "parentfield": "lessons",
                "lesson": lesson.name,
                "idx": max_idx + 1
            }).insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info(f"Added lesson {lesson.name} to chapter {chapter_name} (idx={max_idx + 1})")
        else:
            frappe.logger().info(f"Lesson {lesson.name} already linked to chapter {chapter_name}")
    except Exception as e:
        frappe.log_error(
            f"Failed to link lesson {lesson.name} to chapter {chapter_name}: {str(e)}\n{frappe.get_traceback()}",
            "Recording Lesson Link Error"
        )
        # Lesson was created but not linked - still return the lesson name
        return lesson.name

    frappe.logger().info(f"Successfully created recording lesson: {lesson.name}")
    return lesson.name


def create_orphan_recording(video_id, video_data):
    """
    Create LMS Course Recording without a live class link.

    This is used when we can't match the video to a specific live class.
    Admins can manually link it later.
    """
    # Extract video details
    title = video_data.get("name", f"Recording {video_id}")
    duration = video_data.get("duration", 0)
    embed_data = video_data.get("embed", {})
    pictures = video_data.get("pictures", {})
    created_time = video_data.get("created_time")

    # Get embed URL
    embed_html = embed_data.get("html", "")
    embed_url = extract_embed_url(embed_html) or f"https://player.vimeo.com/video/{video_id}"

    # Get thumbnail
    thumbnail_url = get_best_thumbnail(pictures)

    # Set status to "Uploaded" - the video is on Vimeo and will be playable
    status = "Uploaded"

    # We need a course - try to get a default one or use the first available
    # First, check if there's a default course in settings
    default_course = get_default_course_for_orphans()

    if not default_course:
        frappe.log_error(
            f"Cannot create orphan recording for video {video_id}: No default course configured",
            "Vimeo Processor Error"
        )
        return None

    # Parse date from video creation time
    recorded_on = None
    if created_time:
        try:
            recorded_on = datetime.fromisoformat(created_time.replace("Z", "+00:00")).date()
        except ValueError:
            recorded_on = frappe.utils.today()

    # Create recording
    recording = frappe.new_doc("LMS Course Recording")
    recording.title = title
    recording.course = default_course
    recording.live_class = None  # No live class link
    recording.batch = None
    recording.recorded_on = recorded_on or frappe.utils.today()
    recording.duration = duration
    recording.status = status

    # Vimeo details
    recording.vimeo_video_id = video_id
    recording.vimeo_uri = f"/videos/{video_id}"
    recording.vimeo_player_embed_url = embed_url
    recording.vimeo_privacy_status = video_data.get("privacy", {}).get("view", "unknown")

    if thumbnail_url:
        try:
            recording.thumbnail = download_thumbnail(thumbnail_url, video_id)
        except Exception:
            pass

    recording.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().info(f"Created orphan recording: {recording.name}")

    # Create lesson for orphan recording too
    if default_course:
        frappe.logger().info(f"Creating lesson for orphan recording {recording.name} in course {default_course}")
        try:
            lesson_name = create_lesson_for_recording(
                course=default_course,
                title=title,  # Use video title for orphan recordings
                vimeo_embed_url=embed_url
            )
            if lesson_name:
                frappe.logger().info(f"Created lesson {lesson_name} for orphan recording {recording.name}")
            else:
                frappe.logger().warning(f"create_lesson_for_recording returned None for orphan recording {recording.name}")
        except Exception as e:
            frappe.log_error(
                f"Failed to create lesson for orphan recording {recording.name}: {str(e)}\n{frappe.get_traceback()}",
                "Orphan Recording Lesson Error"
            )

    # Log for admin review
    frappe.log_error(
        f"Created orphan recording {recording.name} for Vimeo video {video_id}. "
        f"Video title: {title}. Please review and link to correct live class.",
        "Orphan Recording Created"
    )

    return recording.name


def get_default_course_for_orphans():
    """
    Get a default course for orphan recordings.

    Returns the first published course, or None if none available.
    In production, this could be configured in settings.
    """
    courses = frappe.get_all(
        "LMS Course",
        filters={"published": 1},
        pluck="name",
        limit=1,
        order_by="creation desc"
    )

    return courses[0] if courses else None


def extract_embed_url(embed_html):
    """Extract the embed URL from Vimeo embed HTML."""
    if not embed_html:
        return None

    # Pattern to find src in iframe
    match = re.search(r'src="([^"]+)"', embed_html)
    if match:
        return match.group(1)

    return None


def get_best_thumbnail(pictures):
    """Get the best quality thumbnail URL from Vimeo pictures data."""
    if not pictures:
        return None

    sizes = pictures.get("sizes", [])
    if not sizes:
        return None

    # Sort by width descending and get the largest
    sizes.sort(key=lambda x: x.get("width", 0), reverse=True)

    # Get a reasonably sized thumbnail (not too large)
    for size in sizes:
        width = size.get("width", 0)
        if 300 <= width <= 1280:
            return size.get("link")

    # Fallback to first available
    return sizes[0].get("link") if sizes else None


def download_thumbnail(url, video_id):
    """Download thumbnail and attach to recording."""
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            # Save to file
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": f"thumbnail_{video_id}.jpg",
                "content": response.content,
                "is_private": 0,
            })
            file_doc.insert(ignore_permissions=True)
            return file_doc.file_url
    except Exception:
        pass

    return None


def apply_vimeo_privacy(video_id):
    """
    Apply privacy settings to the Vimeo video.

    Settings applied:
    - privacy.view: "disable" (hidden from Vimeo, only viewable via embed)
    - privacy.embed: "public" (embeddable on any domain without sign-in)
    - privacy.download: false
    - privacy.add: false
    - privacy.comments: "nobody"
    """
    settings = frappe.get_single("LMS Vimeo Settings")
    access_token = settings.get_password("access_token")

    if not access_token:
        frappe.log_error("Cannot apply privacy: Vimeo access token not configured")
        return False

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.vimeo.*+json;version=3.4",
        "Content-Type": "application/json",
    }

    # Apply privacy settings
    # "disable" = Hide from Vimeo (only viewable via embed, not on vimeo.com)
    # "public" embed = can be embedded on any domain (no sign-in required)
    privacy_payload = {
        "privacy": {
            "view": "disable",
            "embed": "public",
            "download": False,
            "add": False,
            "comments": "nobody",
        }
    }

    try:
        response = requests.patch(
            f"https://api.vimeo.com/videos/{video_id}",
            headers=headers,
            json=privacy_payload,
            timeout=30,
        )

        if response.status_code not in [200, 204]:
            frappe.log_error(
                f"Failed to apply privacy settings: {response.status_code} - {response.text}",
                "Vimeo Privacy Error"
            )
            return False

        # Update recording with final privacy status
        frappe.db.set_value(
            "LMS Course Recording",
            {"vimeo_video_id": video_id},
            "vimeo_privacy_status",
            "unlisted",
        )

        return True

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            f"Vimeo privacy API error: {str(e)}",
            "Vimeo Privacy Error"
        )
        return False


def add_embed_domain(video_id, domain, headers):
    """Add a domain to the video's embed whitelist."""
    try:
        # Clean domain (remove protocol if present)
        domain = domain.replace("https://", "").replace("http://", "")

        response = requests.put(
            f"https://api.vimeo.com/videos/{video_id}/privacy/domains/{domain}",
            headers=headers,
            timeout=30,
        )

        if response.status_code not in [200, 201, 204]:
            frappe.logger().warning(
                f"Failed to add embed domain {domain}: {response.status_code}"
            )

    except requests.exceptions.RequestException as e:
        frappe.logger().warning(f"Error adding embed domain {domain}: {str(e)}")


def check_processing_recordings():
    """
    Scheduled job to check status of processing recordings.

    Updates status to "Uploaded" when transcode is complete.
    """
    processing_recordings = frappe.get_all(
        "LMS Course Recording",
        filters={"status": "Processing", "vimeo_video_id": ["is", "set"]},
        fields=["name", "vimeo_video_id"],
    )

    for rec in processing_recordings:
        video_data = fetch_vimeo_video(rec.vimeo_video_id)
        if not video_data:
            continue

        transcode = video_data.get("transcode", {})
        transcode_status = transcode.get("status", "")

        if transcode_status == "complete":
            frappe.db.set_value("LMS Course Recording", rec.name, "status", "Uploaded")
            frappe.publish_realtime(
                "recording_uploaded",
                {"recording": rec.name},
                after_commit=True,
            )

    frappe.db.commit()


def poll_vimeo_folder():
    """
    Fallback polling job to check Vimeo folder for new recordings.

    This catches any recordings that might have been missed by webhooks.
    Runs every 15 minutes.
    """
    from lms.lms.doctype.lms_vimeo_settings.lms_vimeo_settings import is_vimeo_enabled

    if not is_vimeo_enabled():
        return

    settings = frappe.get_single("LMS Vimeo Settings")
    access_token = settings.get_password("access_token")
    folder_id = settings.default_folder

    if not access_token:
        return

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.vimeo.*+json;version=3.4",
    }

    try:
        # Fetch recent videos from folder (or all videos if no folder specified)
        if folder_id:
            url = f"https://api.vimeo.com/me/projects/{folder_id}/videos"
        else:
            url = "https://api.vimeo.com/me/videos"

        # Get videos from last 24 hours
        params = {
            "per_page": 50,
            "sort": "date",
            "direction": "desc",
        }

        response = requests.get(url, headers=headers, params=params, timeout=60)

        if response.status_code != 200:
            frappe.log_error(
                f"Failed to poll Vimeo folder: {response.status_code}",
                "Vimeo Poll Error"
            )
            return

        data = response.json()
        videos = data.get("data", [])

        for video in videos:
            video_uri = video.get("uri", "")
            video_id = video_uri.split("/")[-1]

            # Skip if already processed
            if frappe.db.exists("LMS Course Recording", {"vimeo_video_id": video_id}):
                continue

            # Check if video is recent (within 24 hours)
            created_time = video.get("created_time")
            if created_time:
                try:
                    # Parse ISO format datetime from Vimeo
                    created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                    # Compare with current time (timezone-aware)
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    if now - created_dt > timedelta(hours=24):
                        continue
                except (ValueError, TypeError):
                    pass

            # Process this recording
            frappe.logger().info(f"Polling: Processing video {video_id}")
            try:
                process_vimeo_recording(video_id, video_uri)
            except Exception as e:
                frappe.log_error(
                    f"Polling: Failed to process video {video_id}: {str(e)}",
                    "Vimeo Poll Error"
                )

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            f"Vimeo folder poll failed: {str(e)}",
            "Vimeo Poll Error"
        )


def fix_vimeo_privacy_settings():
    """
    Fix privacy settings for all existing Vimeo recordings.

    Applies:
    - privacy.view: "disable" (hidden from Vimeo)
    - privacy.embed: "public" (embeddable anywhere without sign-in)

    Returns a summary of what was fixed.
    """
    frappe.logger().info("Starting fix_vimeo_privacy_settings...")

    results = {
        "total_recordings": 0,
        "fixed": 0,
        "failed": 0,
        "skipped": 0,
        "details": []
    }

    # Get all recordings with vimeo video ID
    recordings = frappe.get_all(
        "LMS Course Recording",
        filters={
            "vimeo_video_id": ["is", "set"],
            "status": "Uploaded"
        },
        fields=["name", "vimeo_video_id", "vimeo_privacy_status"],
        order_by="creation asc"
    )

    results["total_recordings"] = len(recordings)
    frappe.logger().info(f"Found {len(recordings)} recordings to check")

    settings = frappe.get_single("LMS Vimeo Settings")
    access_token = settings.get_password("access_token")

    if not access_token:
        frappe.log_error("Cannot fix privacy: Vimeo access token not configured")
        return {"error": "Vimeo access token not configured"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.vimeo.*+json;version=3.4",
        "Content-Type": "application/json",
    }

    for recording in recordings:
        try:
            video_id = recording.vimeo_video_id

            # Apply "Hide from Vimeo" privacy setting (embeddable anywhere)
            privacy_payload = {
                "privacy": {
                    "view": "disable",
                    "embed": "public",
                    "download": False,
                    "add": False,
                    "comments": "nobody",
                }
            }

            response = requests.patch(
                f"https://api.vimeo.com/videos/{video_id}",
                headers=headers,
                json=privacy_payload,
                timeout=30,
            )

            if response.status_code in [200, 204]:
                # Update recording status
                frappe.db.set_value("LMS Course Recording", recording.name, "vimeo_privacy_status", "unlisted")

                results["fixed"] += 1
                results["details"].append({
                    "recording": recording.name,
                    "video_id": video_id,
                    "status": "fixed"
                })
                frappe.logger().info(f"Fixed privacy for {recording.name}")
            else:
                results["failed"] += 1
                results["details"].append({
                    "recording": recording.name,
                    "video_id": video_id,
                    "status": "failed",
                    "reason": f"API error: {response.status_code}"
                })

        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "recording": recording.name,
                "status": "error",
                "reason": str(e)
            })
            frappe.log_error(
                f"Failed to fix privacy for {recording.name}: {str(e)}",
                "Fix Vimeo Privacy Error"
            )

    frappe.db.commit()
    frappe.logger().info(f"fix_vimeo_privacy_settings completed: {results['fixed']} fixed, {results['failed']} failed")

    return results


def fix_missing_recording_lessons():
    """
    Fix all existing recordings that don't have corresponding lessons.

    This function:
    1. Finds all LMS Course Recording documents with a course but no lesson
    2. Creates the "Recordings" chapter and lesson for each

    Can be called manually or via patch after deployment.
    Returns a summary of what was fixed.
    """
    frappe.logger().info("Starting fix_missing_recording_lessons...")

    results = {
        "total_recordings": 0,
        "already_have_lessons": 0,
        "lessons_created": 0,
        "failed": 0,
        "skipped_no_course": 0,
        "skipped_no_vimeo_url": 0,
        "details": []
    }

    # Get all recordings with a course and vimeo embed URL
    recordings = frappe.get_all(
        "LMS Course Recording",
        filters={
            "course": ["is", "set"],
            "status": "Uploaded"
        },
        fields=["name", "title", "course", "live_class", "vimeo_video_id", "vimeo_player_embed_url"],
        order_by="creation asc"
    )

    results["total_recordings"] = len(recordings)
    frappe.logger().info(f"Found {len(recordings)} recordings to check")

    for recording in recordings:
        try:
            # Skip if no course
            if not recording.course:
                results["skipped_no_course"] += 1
                continue

            # Get embed URL
            embed_url = recording.vimeo_player_embed_url
            if not embed_url and recording.vimeo_video_id:
                embed_url = f"https://player.vimeo.com/video/{recording.vimeo_video_id}"

            if not embed_url:
                results["skipped_no_vimeo_url"] += 1
                results["details"].append({
                    "recording": recording.name,
                    "status": "skipped",
                    "reason": "No Vimeo URL"
                })
                continue

            # Determine the title for the lesson
            title = recording.title
            if recording.live_class:
                live_class_title = frappe.db.get_value("LMS Live Class", recording.live_class, "title")
                if live_class_title:
                    title = live_class_title

            # Check if lesson already exists
            expected_lesson_title = f"{title} Recording"
            existing_lesson = frappe.db.get_value(
                "Course Lesson",
                {"title": expected_lesson_title},
                ["name", "chapter"],
                as_dict=True
            )

            if existing_lesson:
                # Verify it's for the same course
                existing_chapter_course = frappe.db.get_value("Course Chapter", existing_lesson.chapter, "course")
                if existing_chapter_course == recording.course:
                    results["already_have_lessons"] += 1
                    results["details"].append({
                        "recording": recording.name,
                        "status": "exists",
                        "lesson": existing_lesson.name
                    })
                    continue

            # Create the lesson
            frappe.logger().info(f"Creating lesson for recording {recording.name}")
            lesson_name = create_lesson_for_recording(
                course=recording.course,
                title=title,
                vimeo_embed_url=embed_url
            )

            if lesson_name:
                results["lessons_created"] += 1
                results["details"].append({
                    "recording": recording.name,
                    "status": "created",
                    "lesson": lesson_name
                })
                frappe.logger().info(f"Created lesson {lesson_name} for recording {recording.name}")
            else:
                results["failed"] += 1
                results["details"].append({
                    "recording": recording.name,
                    "status": "failed",
                    "reason": "create_lesson_for_recording returned None"
                })

        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "recording": recording.name,
                "status": "error",
                "reason": str(e)
            })
            frappe.log_error(
                f"Failed to fix recording {recording.name}: {str(e)}\n{frappe.get_traceback()}",
                "Fix Recording Lesson Error"
            )

    frappe.logger().info(f"fix_missing_recording_lessons completed: {results['lessons_created']} created, {results['already_have_lessons']} already existed, {results['failed']} failed")

    return results
