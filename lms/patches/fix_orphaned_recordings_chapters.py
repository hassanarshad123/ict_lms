"""
Fix recordings that don't have corresponding lessons created.

This patch:
1. Finds all LMS Course Recording documents with a course but no lesson
2. Creates the "Recordings" chapter (if needed) and lesson for each
3. Links orphaned chapters to their courses

Run with: bench --site <sitename> execute lms.patches.fix_orphaned_recordings_chapters.execute
"""

import frappe


def execute():
    """Fix all recordings that don't have corresponding lessons."""
    from lms.lms.doctype.lms_course_recording.vimeo_processor import fix_missing_recording_lessons

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

        # Also fix any orphaned chapters that might still exist
        fix_orphaned_chapters()

    except Exception as e:
        frappe.log_error(
            f"Patch fix_orphaned_recordings_chapters failed: {str(e)}\n{frappe.get_traceback()}",
            "Patch Error"
        )
        raise


def fix_orphaned_chapters():
    """Find and link orphaned Recordings chapters to their courses."""
    print("\nChecking for orphaned Recordings chapters...")

    # Find all "Recordings" chapters
    recordings_chapters = frappe.get_all(
        "Course Chapter",
        filters={"title": "Recordings"},
        fields=["name", "course"]
    )

    if not recordings_chapters:
        print("No 'Recordings' chapters found.")
        return

    fixed_count = 0
    for chapter in recordings_chapters:
        if not chapter.course:
            print(f"Skipping chapter {chapter.name} - no course linked")
            continue

        # Check if this chapter is already linked to the course
        is_linked = frappe.db.exists(
            "Chapter Reference",
            {"parent": chapter.course, "chapter": chapter.name}
        )

        if not is_linked:
            try:
                # Directly insert Chapter Reference to bypass LMS Course permission checks
                max_idx = frappe.db.sql("""
                    SELECT COALESCE(MAX(idx), 0) FROM `tabChapter Reference`
                    WHERE parent = %s
                """, (chapter.course,))[0][0]

                frappe.get_doc({
                    "doctype": "Chapter Reference",
                    "parent": chapter.course,
                    "parenttype": "LMS Course",
                    "parentfield": "chapters",
                    "chapter": chapter.name,
                    "idx": max_idx + 1
                }).insert(ignore_permissions=True)

                print(f"Linked chapter '{chapter.name}' to course '{chapter.course}'")
                fixed_count += 1
            except Exception as e:
                print(f"Failed to link chapter '{chapter.name}': {str(e)}")
        else:
            print(f"Chapter '{chapter.name}' already linked to course '{chapter.course}'")

    frappe.db.commit()
    print(f"\nFixed {fixed_count} orphaned Recordings chapters")


if __name__ == "__main__":
    execute()
