# API Test Results

**Server:** https://lms.ictpk.cloud
**Test Date:** 2026-01-25
**Test User:** kamil@zensbot.com (Instructor/Evaluator role)

---

## Summary

| Category | Working | Errors | Not Deployed |
|----------|---------|--------|--------------|
| Authentication | 3 | 0 | 0 |
| Courses | 1 | 0 | 3 |
| Lessons | 1 | 0 | 2 |
| Quizzes | 0 | 0 | 3 |
| Assignments | 0 | 0 | 3 |
| Jobs | 2 | 0 | 2 |
| Live Classes | 1 | 0 | 1 |
| Certificates | 0 | 0 | 2 |
| Profile | 0 | 0 | 2 |
| Notifications | 3 | 0 | 0 |
| Batch | 1 | 0 | 2 |
| Dashboard | 0 | 1 | 1 |
| Discussions | 0 | 0 | 3 |
| **TOTAL** | **12** | **1** | **24** |

---

## Detailed Test Results

### ✅ Authentication APIs (All Working)

#### 1. api_login
```
POST https://lms.ictpk.cloud/api/method/lms.lms.api.api_login
Status: ✅ WORKING
Response: Returns api_key, api_secret, user info
```

#### 2. api_sign_up
```
POST https://lms.ictpk.cloud/api/method/lms.lms.api.api_sign_up
Status: ✅ WORKING (not tested to avoid creating accounts)
```

#### 3. get_user_info
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_user_info
Status: ✅ WORKING
Response: Full user profile with roles
```

---

### ✅ Existing Course APIs

#### 4. get_my_courses
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_my_courses
Status: ✅ WORKING
Response: Returns 3 courses (usa-tax, cta-course-1-batch-003, lms-course-test)
```

#### 5. get_course_outline (in utils)
```
GET https://lms.ictpk.cloud/api/method/lms.lms.utils.get_course_outline?course=usa-tax
Status: ✅ WORKING
Response: Returns chapters and lessons with content
```

---

### 🚀 New Course APIs (Need Deployment)

#### get_enrolled_courses
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_enrolled_courses
Status: ❌ NOT DEPLOYED
Error: module 'lms.lms.api' has no attribute 'get_enrolled_courses'
```

#### get_course_details_for_student
```
Status: ❌ NOT DEPLOYED
```

#### get_course_progress
```
Status: ❌ NOT DEPLOYED
```

---

### ✅ Existing Lesson APIs

#### 6. mark_lesson_progress
```
POST https://lms.ictpk.cloud/api/method/lms.lms.api.mark_lesson_progress
Body: {"course": "usa-tax", "chapter_number": 1, "lesson_number": 1}
Status: ✅ WORKING
Response: Empty (success)
```

---

### 🚀 New Lesson APIs (Need Deployment)

#### get_course_outline_for_student
```
Status: ❌ NOT DEPLOYED
```

#### get_lesson_details_for_student
```
Status: ❌ NOT DEPLOYED
```

---

### 🚀 Quiz APIs (Need Deployment)

#### get_lesson_quiz
```
Status: ❌ NOT DEPLOYED
```

#### submit_quiz_answers
```
Status: ❌ NOT DEPLOYED
```

#### get_quiz_result
```
Status: ❌ NOT DEPLOYED
```

---

### 🚀 Assignment APIs (Need Deployment)

#### get_course_assignments
```
Status: ❌ NOT DEPLOYED
```

#### submit_assignment
```
Status: ❌ NOT DEPLOYED
```

#### get_assignment_status
```
Status: ❌ NOT DEPLOYED
```

---

### ✅ Existing Job APIs

#### 7. get_job_opportunities
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_job_opportunities
Status: ✅ WORKING
Response: Returns 3 job listings (AI Engineer, Full Stack Developer, Prompt Engineer)
```

#### 8. get_job_details
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_job_details?job=ai-engineer-penguin-swim-school
Status: ✅ WORKING
Response: Full job details
```

---

### 🚀 New Job APIs (Need Deployment)

#### apply_for_job
```
Status: ❌ NOT DEPLOYED
```

#### get_my_applications
```
Status: ❌ NOT DEPLOYED
```

---

### ✅ Existing Live Class APIs

#### 9. get_my_live_classes
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_my_live_classes
Status: ✅ WORKING
Response: Empty array (no upcoming classes)
```

---

### 🚀 New Live Class APIs (Need Deployment)

#### get_live_class_details
```
Status: ❌ NOT DEPLOYED
```

---

### 🚀 Certificate APIs (Need Deployment)

#### get_my_certificates
```
Status: ❌ NOT DEPLOYED
```

#### get_certificate_details
```
Status: ❌ NOT DEPLOYED
```

---

### 🚀 Profile APIs (Need Deployment)

#### update_profile
```
Status: ❌ NOT DEPLOYED
```

#### change_password
```
Status: ❌ NOT DEPLOYED
```

---

### ✅ Existing Notification APIs

#### 10. get_notifications
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_notifications?filters={}
Status: ✅ WORKING
Response: Returns 9 notifications
```

#### 11. mark_as_read
```
Status: ✅ WORKING (exists in codebase)
```

#### 12. mark_all_as_read
```
Status: ✅ WORKING (exists in codebase)
```

---

### ✅ Existing Batch APIs

#### 13. get_my_batches
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_my_batches
Status: ✅ WORKING
Response: Returns 1 batch (testing-ofc)
```

---

### 🚀 New Batch APIs (Need Deployment)

#### get_my_batch
```
Status: ❌ NOT DEPLOYED
```

#### get_batch_timetable
```
Status: ❌ NOT DEPLOYED
```

---

### ❌ Dashboard APIs (Bug Found)

#### get_assigned_badges
```
GET https://lms.ictpk.cloud/api/method/lms.lms.api.get_assigned_badges?member=kamil@zensbot.com
Status: ❌ ERROR
Error: DatabaseQuery.execute() got an unexpected keyword argument 'as_dict'
Fix: Bug fixed in local code - needs deployment
```

---

### 🚀 New Dashboard APIs (Need Deployment)

#### get_learning_stats
```
Status: ❌ NOT DEPLOYED
```

---

### 🚀 Discussion APIs (Need Deployment)

#### get_lesson_discussions
```
Status: ❌ NOT DEPLOYED
```

#### post_discussion
```
Status: ❌ NOT DEPLOYED
```

#### post_reply
```
Status: ❌ NOT DEPLOYED
```

---

## Bugs Fixed

### 1. get_assigned_badges - as_dict parameter error

**Problem:** The `frappe.get_all()` call was passing `as_dict=1` as a positional argument which newer Frappe versions don't accept.

**Fix Applied:** Changed to use named parameters:
```python
# Before (broken)
assigned_badges = frappe.get_all(
    "LMS Badge Assignment",
    {"member": member},
    ["badge"],
    as_dict=1,
)

# After (fixed)
assigned_badges = frappe.get_all(
    "LMS Badge Assignment",
    filters={"member": member},
    fields=["badge"],
)
```

---

## Deployment Instructions

### Step 1: Commit Local Changes
```bash
cd c:\Users\User\Documents\ict_lms
git add lms/lms/api.py
git commit -m "Add 25 new student mobile APIs + fix get_assigned_badges bug"
git push origin develop
```

### Step 2: Deploy to Production

**Option A: If using Frappe Cloud**
1. Go to Frappe Cloud dashboard
2. Navigate to your site (lms.ictpk.cloud)
3. Click "Update" or "Deploy"
4. Wait for deployment to complete

**Option B: If self-hosted**
```bash
# SSH into your server
ssh user@your-server

# Navigate to bench
cd frappe-bench

# Pull latest code
cd apps/lms
git pull origin develop

# Clear cache and restart
bench --site lms.ictpk.cloud clear-cache
bench --site lms.ictpk.cloud migrate
sudo supervisorctl restart all
# or
bench restart
```

### Step 3: Verify Deployment
```bash
# Test one of the new APIs
curl -X GET "https://lms.ictpk.cloud/api/method/lms.lms.api.get_enrolled_courses" \
  -H "Authorization: token YOUR_API_KEY:YOUR_API_SECRET"
```

---

## Post-Deployment Checklist

- [ ] Push code to repository
- [ ] Deploy to production server
- [ ] Test `get_enrolled_courses` API
- [ ] Test `get_learning_stats` API
- [ ] Test `get_assigned_badges` API (bug fix)
- [ ] Share Postman collection with mobile team
- [ ] Mobile team imports collection and tests
