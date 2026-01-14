-- Check if Recordings chapters exist
SELECT
    ch.name as chapter_name,
    ch.title,
    ch.course,
    c.title as course_title,
    ch.creation,
    ch.modified
FROM `tabCourse Chapter` ch
JOIN `tabLMS Course` c ON ch.course = c.name
WHERE ch.title = 'Recordings'
ORDER BY ch.modified DESC;

-- Check Chapter References for Recordings chapters
SELECT
    cr.name,
    cr.parent as course,
    cr.chapter,
    cr.idx,
    cc.title as chapter_title
FROM `tabChapter Reference` cr
JOIN `tabCourse Chapter` cc ON cr.chapter = cc.name
WHERE cc.title = 'Recordings'
ORDER BY cr.idx;

-- Check lessons in Recordings chapters
SELECT
    l.name as lesson_name,
    l.title as lesson_title,
    l.chapter,
    c.title as chapter_title,
    l.course,
    l.youtube,
    l.include_in_preview,
    LENGTH(l.body) as body_length,
    l.creation,
    l.modified
FROM `tabCourse Lesson` l
JOIN `tabCourse Chapter` c ON l.chapter = c.name
WHERE c.title = 'Recordings'
ORDER BY l.modified DESC
LIMIT 10;

-- Check Lesson References for lessons in Recordings chapters
SELECT
    lr.name,
    lr.parent as chapter,
    lr.lesson,
    lr.idx,
    l.title as lesson_title,
    c.title as chapter_title
FROM `tabLesson Reference` lr
JOIN `tabCourse Lesson` l ON lr.lesson = l.name
JOIN `tabCourse Chapter` c ON lr.parent = c.name
WHERE c.title = 'Recordings'
ORDER BY lr.idx;

-- Check recent LMS Course Recordings
SELECT
    name,
    title,
    course,
    status,
    vimeo_video_id,
    vimeo_player_embed_url,
    live_class,
    batch,
    instructor,
    duration,
    creation,
    modified
FROM `tabLMS Course Recording`
ORDER BY modified DESC
LIMIT 10;

-- Check recent Live Classes
SELECT
    name,
    title,
    date,
    time,
    batch_name,
    host,
    creation,
    modified
FROM `tabLMS Live Class`
ORDER BY modified DESC
LIMIT 10;
