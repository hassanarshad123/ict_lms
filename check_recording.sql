-- SQL queries to check recording processing status

-- 1. Check if any Live Classes were matched and updated (last 10)
SELECT
    name,
    title,
    date,
    recording_url,
    recording_available,
    batch_name,
    modified
FROM `tabLMS Live Class`
WHERE recording_available = 1
ORDER BY modified DESC
LIMIT 10;

-- 2. Check if any lessons were created in Recordings chapter (last 10)
SELECT
    l.name as lesson_name,
    l.title as lesson_title,
    c.name as chapter_name,
    c.title as chapter_title,
    co.name as course_name,
    co.title as course_title,
    l.creation,
    l.youtube as video_url
FROM `tabCourse Lesson` l
JOIN `tabCourse Chapter` c ON l.chapter = c.name
JOIN `tabLMS Course` co ON l.course = co.name
WHERE c.title = 'Recordings'
ORDER BY l.creation DESC
LIMIT 10;

-- 3. Check if "Recordings" chapters exist
SELECT
    ch.name,
    ch.title,
    ch.course,
    c.title as course_title,
    ch.creation
FROM `tabCourse Chapter` ch
JOIN `tabLMS Course` c ON ch.course = c.name
WHERE ch.title = 'Recordings'
ORDER BY ch.creation DESC;

-- 4. Check recent Live Classes (to verify matching data)
SELECT
    name,
    title,
    date,
    time,
    meeting_id,
    batch_name,
    recording_url,
    recording_available
FROM `tabLMS Live Class`
WHERE date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
ORDER BY date DESC, time DESC
LIMIT 20;
