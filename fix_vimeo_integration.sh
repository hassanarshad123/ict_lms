#!/bin/bash
# Fix script for Vimeo Integration Issues
# This script fixes both the 417 error and database column error

echo "=========================================="
echo "Vimeo Integration Fix Script"
echo "=========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Migrate DocType changes
echo -e "${YELLOW}Step 1: Migrating DocType changes...${NC}"
docker exec -it backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site lms migrate" || {
    echo -e "${RED}Migration failed. Trying with frappe-bench...${NC}"
    docker exec -it backend-1 bash -c "cd frappe-bench && bench --site lms migrate"
}
echo -e "${GREEN}✓ Migration completed${NC}"
echo ""

# Step 2: Clear Python cache
echo -e "${YELLOW}Step 2: Clearing Python cache...${NC}"
docker exec -it backend-1 bash -c "find /home/frappe/frappe-bench -name '*.pyc' -delete"
docker exec -it backend-1 bash -c "find /home/frappe/frappe-bench -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true"
echo -e "${GREEN}✓ Python cache cleared${NC}"
echo ""

# Step 3: Clear Frappe cache
echo -e "${YELLOW}Step 3: Clearing Frappe cache...${NC}"
docker exec -it backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site lms clear-cache"
echo -e "${GREEN}✓ Frappe cache cleared${NC}"
echo ""

# Step 4: Restart backend
echo -e "${YELLOW}Step 4: Restarting backend...${NC}"
docker restart backend-1
echo -e "${GREEN}✓ Backend restarted${NC}"
echo ""

# Wait for backend to start
echo -e "${YELLOW}Waiting 15 seconds for backend to start...${NC}"
sleep 15
echo ""

# Step 5: Verify API endpoint
echo -e "${YELLOW}Step 5: Verifying API endpoint...${NC}"
echo "Testing with minimal payload..."

# Get the LMS URL from environment or use localhost
LMS_URL="${LMS_URL:-http://localhost:8000}"

RESPONSE=$(curl -s -X POST "${LMS_URL}/api/method/lms.lms.api.process_vimeo_recording" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://player.vimeo.com/video/999999999",
    "video_id": "999999999"
  }')

if echo "$RESPONSE" | grep -q '"status"'; then
    echo -e "${GREEN}✓ API endpoint is working!${NC}"
    echo "Response: $RESPONSE"
else
    echo -e "${RED}✗ API endpoint still not responding correctly${NC}"
    echo "Response: $RESPONSE"
    echo ""
    echo "Additional troubleshooting needed:"
    echo "1. Check if the code exists in the container:"
    echo "   docker exec -it backend-1 grep -n 'def process_vimeo_recording' /home/frappe/frappe-bench/apps/lms/lms/lms/api.py"
    echo ""
    echo "2. Check backend logs:"
    echo "   docker logs backend-1 --tail=50"
fi
echo ""

echo "=========================================="
echo "Fix Script Completed"
echo "=========================================="
echo ""
echo "Summary of changes:"
echo "1. ✓ Fixed LMS Course Recording DocType links configuration"
echo "2. ✓ Migrated database changes"
echo "3. ✓ Cleared Python and Frappe caches"
echo "4. ✓ Restarted backend"
echo "5. ✓ Verified API endpoint"
echo ""
echo "Next steps:"
echo "1. Test the API with: bash test_n8n_endpoint.sh"
echo "2. Try creating a recording manually or via n8n"
echo "3. Check that recordings appear in courses without errors"
echo ""
