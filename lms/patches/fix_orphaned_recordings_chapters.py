"""
Fix orphaned Recordings chapters that were created but not linked to their courses.

This patch finds all "Recordings" chapters that exist in the Course Chapter table
but are not linked to their course via the Chapter Reference table, and links them.

Run with: bench --site <sitename> execute lms.patches.fix_orphaned_recordings_chapters.execute
"""

import frappe


def execute():
    """Find and link orphaned Recordings chapters to their courses."""
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
            # Link it to the course
            course_doc = frappe.get_doc("LMS Course", chapter.course)
            course_doc.append("chapters", {"chapter": chapter.name})
            course_doc.save(ignore_permissions=True)
            print(f"Linked chapter '{chapter.name}' to course '{chapter.course}'")
            fixed_count += 1
        else:
            print(f"Chapter '{chapter.name}' already linked to course '{chapter.course}'")

    frappe.db.commit()
    print(f"\nFixed {fixed_count} orphaned Recordings chapters")


if __name__ == "__main__":
    execute()
