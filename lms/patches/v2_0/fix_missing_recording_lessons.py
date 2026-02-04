"""
Fix all recordings that don't have corresponding lessons created.

This patch:
1. Finds all LMS Course Recording documents with a course but no lesson
2. Creates the "Recordings" chapter (if needed) and lesson for each
3. Uses direct database inserts to bypass permission checks

Run manually: bench --site <sitename> execute lms.patches.v2_0.fix_missing_recording_lessons.execute
"""

import frappe


def execute():
    """Fix all recordings that don't have corresponding lessons."""
    from lms.lms.doctype.lms_course_recording.vimeo_processor import fix_missing_recording_lessons

    frappe.logger().info("Starting patch: fix_missing_recording_lessons")
    print("Starting fix for missing recording lessons...")

    try:
        results = fix_missing_recording_lessons()

        print(f"\n=== Results ===")
        print(f"Total recordings checked: {results['total_recordings']}")
        print(f"Already have lessons: {results['already_have_lessons']}")
        print(f"Lessons created: {results['lessons_created']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped (no course): {results['skipped_no_course']}")
        print(f"Skipped (no Vimeo URL): {results['skipped_no_vimeo_url']}")

        if results['failed'] > 0:
            print(f"\nCheck Error Log for 'Fix Recording Lesson Error' entries for details on failures.")

        frappe.logger().info(f"Patch completed: {results['lessons_created']} lessons created, {results['failed']} failed")

    except Exception as e:
        frappe.log_error(
            f"Patch fix_missing_recording_lessons failed: {str(e)}\n{frappe.get_traceback()}",
            "Patch Error"
        )
        print(f"ERROR: {str(e)}")
        raise
