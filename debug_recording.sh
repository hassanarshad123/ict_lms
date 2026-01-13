#!/bin/bash
# Debug script to check recording processing status

echo "=========================================="
echo "Recording Processing Debug Script"
echo "=========================================="
echo ""

# Check backend logs for the specific request
echo "1. Checking backend logs for [n8n Vimeo] entries..."
echo "---"
docker logs backend-1 --tail=100 2>&1 | grep "\[n8n Vimeo\]"
echo ""

# Check if the response was "no match"
echo "2. Checking for recent API calls..."
echo "---"
docker logs frontend-lms-1 --tail=20 2>&1 | grep "process_vimeo_recording"
echo ""

# Check database for recent Live Classes
echo "3. Checking database for Live Classes with recordings..."
echo "---"
docker exec -it backend-1 bench --site lms mariadb -e "
SELECT
    name,
    title,
    date,
    recording_url,
    recording_available
FROM \`tabLMS Live Class\`
WHERE recording_available = 1
ORDER BY modified DESC
LIMIT 5;
" 2>/dev/null || echo "Could not query database. Try manually."
echo ""

# Check for Recordings chapters
echo "4. Checking for 'Recordings' chapters..."
echo "---"
docker exec -it backend-1 bench --site lms mariadb -e "
SELECT
    ch.name,
    ch.title,
    c.title as course_title,
    ch.creation
FROM \`tabCourse Chapter\` ch
JOIN \`tabLMS Course\` c ON ch.course = c.name
WHERE ch.title = 'Recordings'
ORDER BY ch.creation DESC
LIMIT 5;
" 2>/dev/null || echo "Could not query database. Try manually."
echo ""

echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "If no recordings found, possible reasons:"
echo "1. No matching Live Class exists"
echo "2. Live Class title/date doesn't match video"
echo "3. meeting_id not present or doesn't match"
echo "4. created_time is missing or incorrect"
echo ""
echo "To test matching, create a Live Class with:"
echo "  - Title matching your video title"
echo "  - Date matching video creation date"
echo "  - meeting_id field populated (if using Zoom)"
echo ""
