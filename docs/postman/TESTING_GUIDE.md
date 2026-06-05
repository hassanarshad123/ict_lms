# API Testing Guide

This guide explains how to test the LMS Student Mobile App APIs.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Testing with Postman](#testing-with-postman)
3. [Testing with cURL](#testing-with-curl)
4. [Testing with Python](#testing-with-python)
5. [Testing Workflow](#testing-workflow)
6. [Common Issues & Solutions](#common-issues--solutions)

---

## Prerequisites

### 1. LMS Server Running

Make sure your Frappe/LMS server is running:

```bash
# In your frappe-bench directory
bench start
```

Your server should be accessible at `http://localhost:8000` or your configured URL.

### 2. Test User Account

Create a test student account either:
- Through the LMS web interface
- Using the Sign Up API (shown below)

### 3. Test Data

Ensure you have:
- At least one published course
- Student enrolled in the course
- Some lessons, quizzes, and assignments

---

## Testing with Postman

### Step 1: Import Collection

1. Open Postman
2. Click **Import** button
3. Select `docs/postman/LMS_Student_Mobile_API.postman_collection.json`
4. Collection will appear in sidebar

### Step 2: Create Environment

1. Click **Environments** (gear icon)
2. Click **Add** to create new environment
3. Name it "LMS Local" or "LMS Production"
4. Add these variables:

| Variable | Initial Value | Current Value |
|----------|---------------|---------------|
| `base_url` | `http://localhost:8000` | `http://localhost:8000` |
| `api_key` | (leave empty) | (leave empty) |
| `api_secret` | (leave empty) | (leave empty) |

5. Click **Save**
6. Select the environment from dropdown

### Step 3: Test Authentication

1. Open **Authentication > Login** request
2. Update the body with valid credentials:
```json
{
    "usr": "your-test-student@example.com",
    "pwd": "your-password"
}
```
3. Click **Send**
4. Copy `api_key` and `api_secret` from response
5. Update environment variables with these values

### Step 4: Test Other Endpoints

Now all authenticated endpoints will work. Test in this order:

1. **Get User Info** - Verify authentication works
2. **Get Enrolled Courses** - See enrolled courses
3. **Get Course Outline** - See course structure
4. **Get Lesson Details** - View lesson content
5. Continue with other endpoints...

### Step 5: Automate Token Storage (Optional)

Add this script to the **Login** request's **Tests** tab:

```javascript
if (pm.response.code === 200) {
    var jsonData = pm.response.json();
    if (jsonData.message) {
        pm.environment.set("api_key", jsonData.message.api_key);
        pm.environment.set("api_secret", jsonData.message.api_secret);
        console.log("Tokens saved to environment!");
    }
}
```

Now tokens are automatically saved after login.

---

## Testing with cURL

### 1. Login

```bash
curl -X POST "http://localhost:8000/api/method/lms.lms.api.api_login" \
  -H "Content-Type: application/json" \
  -d '{"usr": "student@example.com", "pwd": "password123"}'
```

**Response:**
```json
{
  "message": {
    "message": "Login successful",
    "api_key": "abc123",
    "api_secret": "xyz789",
    "user": {...}
  }
}
```

### 2. Set Token Variables

```bash
# Linux/Mac
export API_KEY="abc123"
export API_SECRET="xyz789"
export BASE_URL="http://localhost:8000"

# Windows PowerShell
$env:API_KEY = "abc123"
$env:API_SECRET = "xyz789"
$env:BASE_URL = "http://localhost:8000"
```

### 3. Test Authenticated Endpoints

```bash
# Get User Info
curl -X GET "$BASE_URL/api/method/lms.lms.api.get_user_info" \
  -H "Authorization: token $API_KEY:$API_SECRET"

# Get Enrolled Courses
curl -X GET "$BASE_URL/api/method/lms.lms.api.get_enrolled_courses" \
  -H "Authorization: token $API_KEY:$API_SECRET"

# Get Course Details
curl -X GET "$BASE_URL/api/method/lms.lms.api.get_course_details_for_student?course=your-course-id" \
  -H "Authorization: token $API_KEY:$API_SECRET"

# Get Course Outline
curl -X GET "$BASE_URL/api/method/lms.lms.api.get_course_outline_for_student?course=your-course-id" \
  -H "Authorization: token $API_KEY:$API_SECRET"

# Get Lesson Details
curl -X GET "$BASE_URL/api/method/lms.lms.api.get_lesson_details_for_student?lesson=your-lesson-id" \
  -H "Authorization: token $API_KEY:$API_SECRET"

# Mark Lesson Complete
curl -X POST "$BASE_URL/api/method/lms.lms.api.mark_lesson_progress" \
  -H "Authorization: token $API_KEY:$API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"course": "course-id", "chapter_number": 1, "lesson_number": 1}'

# Get Learning Stats
curl -X GET "$BASE_URL/api/method/lms.lms.api.get_learning_stats" \
  -H "Authorization: token $API_KEY:$API_SECRET"
```

---

## Testing with Python

### Setup

```bash
pip install requests
```

### Test Script

```python
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "student@example.com"
PASSWORD = "password123"

class LMSClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.api_key = None
        self.api_secret = None

    def _get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_secret:
            headers["Authorization"] = f"token {self.api_key}:{self.api_secret}"
        return headers

    def _call(self, method, endpoint, data=None, params=None):
        url = f"{self.base_url}/api/method/{endpoint}"
        response = requests.request(
            method,
            url,
            headers=self._get_headers(),
            json=data,
            params=params
        )
        return response.json()

    # Authentication
    def login(self, email, password):
        result = self._call("POST", "lms.lms.api.api_login", {
            "usr": email,
            "pwd": password
        })
        if "message" in result:
            self.api_key = result["message"]["api_key"]
            self.api_secret = result["message"]["api_secret"]
            print(f"✓ Logged in as {result['message']['user']['full_name']}")
        return result

    def get_user_info(self):
        return self._call("GET", "lms.lms.api.get_user_info")

    # Courses
    def get_enrolled_courses(self, start=0, page_length=20):
        return self._call("GET", "lms.lms.api.get_enrolled_courses", params={
            "start": start,
            "page_length": page_length
        })

    def get_course_details(self, course):
        return self._call("GET", "lms.lms.api.get_course_details_for_student", params={
            "course": course
        })

    def get_course_progress(self, course):
        return self._call("GET", "lms.lms.api.get_course_progress", params={
            "course": course
        })

    def get_course_outline(self, course):
        return self._call("GET", "lms.lms.api.get_course_outline_for_student", params={
            "course": course
        })

    # Lessons
    def get_lesson_details(self, lesson):
        return self._call("GET", "lms.lms.api.get_lesson_details_for_student", params={
            "lesson": lesson
        })

    def mark_lesson_complete(self, course, chapter_number, lesson_number):
        return self._call("POST", "lms.lms.api.mark_lesson_progress", {
            "course": course,
            "chapter_number": chapter_number,
            "lesson_number": lesson_number
        })

    # Quizzes
    def get_quiz(self, quiz):
        return self._call("GET", "lms.lms.api.get_lesson_quiz", params={
            "quiz": quiz
        })

    def submit_quiz(self, quiz, answers):
        return self._call("POST", "lms.lms.api.submit_quiz_answers", {
            "quiz": quiz,
            "answers": answers
        })

    # Dashboard
    def get_learning_stats(self):
        return self._call("GET", "lms.lms.api.get_learning_stats")

    # Certificates
    def get_certificates(self):
        return self._call("GET", "lms.lms.api.get_my_certificates")


# Run Tests
if __name__ == "__main__":
    client = LMSClient(BASE_URL)

    # Test 1: Login
    print("\n--- Test 1: Login ---")
    result = client.login(EMAIL, PASSWORD)
    print(json.dumps(result, indent=2))

    # Test 2: Get User Info
    print("\n--- Test 2: Get User Info ---")
    result = client.get_user_info()
    print(json.dumps(result, indent=2))

    # Test 3: Get Enrolled Courses
    print("\n--- Test 3: Get Enrolled Courses ---")
    result = client.get_enrolled_courses()
    print(json.dumps(result, indent=2))

    # Get first course for further tests
    if result.get("message", {}).get("courses"):
        course_id = result["message"]["courses"][0]["name"]

        # Test 4: Get Course Details
        print(f"\n--- Test 4: Get Course Details ({course_id}) ---")
        result = client.get_course_details(course_id)
        print(json.dumps(result, indent=2))

        # Test 5: Get Course Outline
        print(f"\n--- Test 5: Get Course Outline ({course_id}) ---")
        result = client.get_course_outline(course_id)
        print(json.dumps(result, indent=2))

        # Test 6: Get Course Progress
        print(f"\n--- Test 6: Get Course Progress ({course_id}) ---")
        result = client.get_course_progress(course_id)
        print(json.dumps(result, indent=2))

    # Test 7: Get Learning Stats
    print("\n--- Test 7: Get Learning Stats ---")
    result = client.get_learning_stats()
    print(json.dumps(result, indent=2))

    # Test 8: Get Certificates
    print("\n--- Test 8: Get Certificates ---")
    result = client.get_certificates()
    print(json.dumps(result, indent=2))

    print("\n✓ All tests completed!")
```

Save as `test_api.py` and run:

```bash
python test_api.py
```

---

## Testing Workflow

### Complete User Flow Test

Test the complete student journey:

```
1. AUTHENTICATION
   └── Login → Get credentials

2. DASHBOARD
   ├── Get User Info → Verify user
   ├── Get Learning Stats → Dashboard data
   └── Get My Batches → Enrolled batches

3. COURSES
   ├── Get Enrolled Courses → List courses
   ├── Get Course Details → Full course info
   ├── Get Course Progress → Progress details
   └── Get Course Outline → Chapters & lessons

4. LEARNING
   ├── Get Lesson Details → View content
   ├── Mark Lesson Complete → Track progress
   ├── Get Quiz → Load questions
   └── Submit Quiz → Get result

5. ASSIGNMENTS
   ├── Get Course Assignments → List assignments
   ├── Submit Assignment → Submit work
   └── Get Assignment Status → Check feedback

6. LIVE CLASSES
   ├── Get Upcoming Classes → Scheduled classes
   └── Get Live Class Details → Join URL

7. CERTIFICATES
   ├── Get My Certificates → List earned
   └── Get Certificate Details → Download
```

### Test Each Response

For each endpoint, verify:

- [ ] HTTP status code is 200
- [ ] Response contains `message` wrapper
- [ ] Data structure matches documentation
- [ ] Pagination works (for list endpoints)
- [ ] Error handling works (invalid inputs)

---

## Common Issues & Solutions

### Issue 1: 401 Unauthorized

**Cause:** Invalid or missing token

**Solution:**
```bash
# Check token format
Authorization: token API_KEY:API_SECRET

# Not this:
Authorization: Bearer API_KEY:API_SECRET
Authorization: token API_KEY API_SECRET
```

### Issue 2: 403 Forbidden

**Cause:** User doesn't have permission

**Solution:**
- Ensure user has "LMS Student" role
- Check enrollment status for course-specific endpoints

### Issue 3: 417 Expectation Failed

**Cause:** Validation error

**Solution:**
- Check required parameters are provided
- Verify parameter values are valid IDs

### Issue 4: 500 Internal Server Error

**Cause:** Server-side error

**Solution:**
- Check Frappe error logs: `bench --site your-site.local show-logs`
- Verify database is running
- Check for Python syntax errors in API code

### Issue 5: CORS Error (Browser Testing)

**Cause:** Cross-origin request blocked

**Solution:**
Add to `site_config.json`:
```json
{
    "allow_cors": "*"
}
```

Then restart bench:
```bash
bench restart
```

### Issue 6: Empty Response

**Cause:** User not enrolled or no data

**Solution:**
- Verify user is enrolled in courses
- Check course has chapters and lessons
- Ensure course is published

---

## Debug Tips

### Enable Debug Mode

```python
# In api.py, add at top of function:
import frappe
frappe.log_error(f"Input: {course}", "Debug get_course_details")
```

Check logs:
```bash
bench --site your-site.local show-logs
```

### Check Database Directly

```bash
bench --site your-site.local mariadb

# Then in MariaDB:
SELECT name, member, course, progress FROM `tabLMS Enrollment` WHERE member = 'student@example.com';
```

### Test Specific Endpoint

```bash
bench --site your-site.local execute lms.lms.api.get_enrolled_courses
```

---

## Next Steps

After testing APIs locally:

1. **Deploy to staging** and test with real data
2. **Share Postman collection** with mobile team
3. **Set up API monitoring** for production
4. **Document any customizations** needed for your use case
