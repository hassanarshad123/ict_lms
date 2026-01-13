#!/bin/bash
# Quick verification script for the API endpoint

LMS_URL="${1:-http://localhost:8000}"

echo "Testing API endpoint: ${LMS_URL}/api/method/lms.lms.api.process_vimeo_recording"
echo ""

# Test 1: Check if function exists in code
echo "1. Checking if function exists in code..."
docker exec backend-1 grep -c "def process_vimeo_recording" /home/frappe/frappe-bench/apps/lms/lms/lms/api.py 2>/dev/null || echo "Could not check file"
echo ""

# Test 2: Test API with minimal payload
echo "2. Testing API with minimal payload..."
curl -v -X POST "${LMS_URL}/api/method/lms.lms.api.process_vimeo_recording" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://player.vimeo.com/video/999999999",
    "video_id": "999999999"
  }' 2>&1 | head -30
echo ""

# Test 3: Check recent backend logs
echo "3. Checking recent backend logs for errors..."
docker logs backend-1 --tail=20 2>&1 | tail -10
echo ""
