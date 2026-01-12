#!/bin/bash
# Test script for n8n Vimeo integration endpoint
# Usage: bash test_n8n_endpoint.sh <YOUR_LMS_URL>

LMS_URL="${1:-http://localhost:8000}"
ENDPOINT="${LMS_URL}/api/method/lms.lms.api.process_vimeo_recording"

echo "================================"
echo "Testing n8n Vimeo Integration"
echo "================================"
echo "Endpoint: $ENDPOINT"
echo ""

# Test 1: Missing required fields
echo "Test 1: Missing required fields (should return validation error)"
echo "---"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"video_id": "123"}'
echo -e "\n"

# Test 2: Invalid video_url
echo "Test 2: Invalid video_url (should return validation error)"
echo "---"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://youtube.com/watch?v=123",
    "video_id": "123"
  }'
echo -e "\n"

# Test 3: Valid payload but no match (example)
echo "Test 3: Valid payload - no matching live class expected"
echo "---"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://player.vimeo.com/video/1153210218",
    "video_id": "1153210218",
    "created_time": "2026-01-11T15:46:00Z",
    "meeting_id": "12345678901",
    "title": "Test Class Recording",
    "description": "This is a test recording. Meeting ID: 12345678901",
    "duration": 3600
  }'
echo -e "\n"

# Test 4: Valid payload with Unix timestamp
echo "Test 4: Valid payload with Unix timestamp"
echo "---"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://player.vimeo.com/video/9999999",
    "video_id": "9999999",
    "created_time": 1736609160,
    "title": "Another Test Class",
    "description": "Meeting ID: 98765432101"
  }'
echo -e "\n"

echo "================================"
echo "Tests completed!"
echo "================================"
echo ""
echo "Notes:"
echo "- Expected: Tests 1-2 should return validation errors"
echo "- Expected: Tests 3-4 should return 'no matching live class found' (unless you have matching data)"
echo "- To test successful match, create a Live Class with matching title/date/meeting_id"
echo ""
