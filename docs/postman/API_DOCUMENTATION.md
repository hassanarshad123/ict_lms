# LMS Student Mobile App - Complete API Documentation

**Version:** 1.0
**Base URL:** `https://your-lms-instance.com`
**Authentication:** Token-based (`Authorization: token <api_key>:<api_secret>`)

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Courses API](#courses-api)
4. [Lessons API](#lessons-api)
5. [Quizzes API](#quizzes-api)
6. [Assignments API](#assignments-api)
7. [Jobs API](#jobs-api)
8. [Live Classes API](#live-classes-api)
9. [Certificates API](#certificates-api)
10. [Profile API](#profile-api)
11. [Notifications API](#notifications-api)
12. [Batch API](#batch-api)
13. [Dashboard API](#dashboard-api)
14. [Discussions API](#discussions-api)
15. [Error Handling](#error-handling)

---

## Overview

### Base URL Format

All API calls follow this pattern:
```
POST/GET {base_url}/api/method/lms.lms.api.{endpoint_name}
```

### Response Format

All responses are wrapped in a `message` object:
```json
{
    "message": {
        // Response data here
    }
}
```

### Pagination

List endpoints support pagination with:
- `start` - Offset (default: 0)
- `page_length` - Records per page (default: 20)

Response includes:
```json
{
    "items": [...],
    "total_count": 100
}
```

---

## Authentication

### Login

Authenticate user and get API tokens.

**Endpoint:** `POST /api/method/lms.lms.api.api_login`
**Auth Required:** No

**Request Body:**
```json
{
    "usr": "student@example.com",
    "pwd": "password123"
}
```

**Response:**
```json
{
    "message": {
        "message": "Login successful",
        "api_key": "a1b2c3d4e5f6g7h",
        "api_secret": "x9y8z7w6v5u4t3s",
        "user": {
            "name": "student@example.com",
            "email": "student@example.com",
            "full_name": "John Doe",
            "username": "johndoe",
            "user_image": "/files/profile.jpg",
            "is_admin": false,
            "is_student": true,
            "roles": ["LMS Student"]
        }
    }
}
```

**Usage in Mobile App:**
```javascript
// Store tokens securely
await SecureStore.setItemAsync('api_key', response.api_key);
await SecureStore.setItemAsync('api_secret', response.api_secret);

// Use in subsequent requests
const headers = {
    'Authorization': `token ${api_key}:${api_secret}`,
    'Content-Type': 'application/json'
};
```

---

### Sign Up

Register a new student account.

**Endpoint:** `POST /api/method/lms.lms.api.api_sign_up`
**Auth Required:** No

**Request Body:**
```json
{
    "email": "newstudent@example.com",
    "full_name": "Jane Smith",
    "password": "securepassword123"
}
```

**Response:**
```json
{
    "message": {
        "message": "Signup successful",
        "api_key": "h7g6f5e4d3c2b1a",
        "api_secret": "s3t4u5v6w7x8y9z",
        "user": {
            "name": "newstudent@example.com",
            "email": "newstudent@example.com",
            "full_name": "Jane Smith",
            "username": "janesmith",
            "user_image": null,
            "is_admin": false,
            "is_student": true,
            "roles": ["LMS Student"]
        }
    }
}
```

**Validation:**
- Email must be valid format
- Password minimum 6 characters
- Email must not already exist

---

### Get User Info

Get current authenticated user's profile.

**Endpoint:** `GET /api/method/lms.lms.api.get_user_info`
**Auth Required:** Yes

**Response:**
```json
{
    "message": {
        "name": "student@example.com",
        "email": "student@example.com",
        "enabled": 1,
        "user_image": "/files/profile.jpg",
        "full_name": "John Doe",
        "user_type": "Website User",
        "username": "johndoe",
        "roles": ["LMS Student"],
        "is_admin": false,
        "is_course_creator": false,
        "is_teacher": false,
        "is_student": true
    }
}
```

---

## Courses API

### Get Enrolled Courses

Get all courses the student is enrolled in.

**Endpoint:** `GET /api/method/lms.lms.api.get_enrolled_courses`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start` | int | 0 | Pagination offset |
| `page_length` | int | 20 | Records per page |

**Response:**
```json
{
    "message": {
        "courses": [
            {
                "name": "python-fundamentals",
                "title": "Python Fundamentals",
                "image": "/files/python-course.jpg",
                "short_introduction": "Learn Python from scratch",
                "published": 1,
                "lessons": 24,
                "video_link": "https://youtube.com/embed/xxx",
                "instructors": [
                    {
                        "name": "instructor@example.com",
                        "full_name": "Dr. Smith",
                        "user_image": "/files/smith.jpg",
                        "username": "drsmith"
                    }
                ],
                "progress": 45.5,
                "current_lesson": "lesson-12",
                "current_lesson_title": "Functions in Python",
                "enrollment_date": "2024-01-15",
                "enrollment_from_batch": null,
                "completed_lessons": 11,
                "total_lessons": 24
            }
        ],
        "total_count": 5
    }
}
```

---

### Get Course Details

Get complete details for a specific course.

**Endpoint:** `GET /api/method/lms.lms.api.get_course_details_for_student`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course` | string | Yes | Course ID/name |

**Response:**
```json
{
    "message": {
        "name": "python-fundamentals",
        "title": "Python Fundamentals",
        "image": "/files/python-course.jpg",
        "short_introduction": "Learn Python from scratch",
        "description": "<p>Full HTML description...</p>",
        "video_link": "https://youtube.com/embed/xxx",
        "published": 1,
        "lessons": 24,
        "rating": "4.5",
        "paid_course": 0,
        "course_price": 0,
        "currency": null,
        "enable_certification": 1,
        "paid_certificate": 0,
        "instructors": [...],
        "total_chapters": 5,
        "total_lessons": 24,
        "membership": {
            "name": "enrollment-001",
            "progress": 45.5,
            "current_lesson": "lesson-12",
            "enrollment_date": "2024-01-15",
            "enrollment_from_batch": null
        },
        "certificate_earned": false,
        "review_count": 15,
        "average_rating": 4.5
    }
}
```

---

### Get Course Progress

Get detailed progress for a course.

**Endpoint:** `GET /api/method/lms.lms.api.get_course_progress`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course` | string | Yes | Course ID/name |

**Response:**
```json
{
    "message": {
        "course": "python-fundamentals",
        "overall_progress": 45.5,
        "total_lessons": 24,
        "completed_lessons": 11,
        "total_chapters": 5,
        "completed_chapters": 2,
        "quizzes_attempted": 3,
        "quizzes_passed": 2,
        "assignments_submitted": 4,
        "assignments_graded": 3,
        "current_lesson": {
            "name": "lesson-12",
            "title": "Functions in Python",
            "chapter": "Chapter 3: Functions",
            "number": "3-2"
        },
        "last_activity": "2024-01-20 14:30:00"
    }
}
```

---

### Get Course Outline

Get course structure with chapters and lessons.

**Endpoint:** `GET /api/method/lms.lms.api.get_course_outline_for_student`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course` | string | Yes | Course ID/name |

**Response:**
```json
{
    "message": {
        "course": "python-fundamentals",
        "title": "Python Fundamentals",
        "total_lessons": 24,
        "is_enrolled": true,
        "chapters": [
            {
                "name": "chapter-1",
                "title": "Getting Started",
                "idx": 1,
                "is_scorm_package": false,
                "lesson_count": 5,
                "completed_count": 5,
                "lessons": [
                    {
                        "name": "lesson-1",
                        "title": "Introduction to Python",
                        "number": "1-1",
                        "idx": 1,
                        "include_in_preview": true,
                        "has_video": true,
                        "has_quiz": false,
                        "has_assignment": false,
                        "is_complete": true
                    },
                    {
                        "name": "lesson-2",
                        "title": "Installing Python",
                        "number": "1-2",
                        "idx": 2,
                        "include_in_preview": false,
                        "has_video": true,
                        "has_quiz": true,
                        "has_assignment": false,
                        "is_complete": true
                    }
                ]
            }
        ]
    }
}
```

---

## Lessons API

### Get Lesson Details

Get full lesson content.

**Endpoint:** `GET /api/method/lms.lms.api.get_lesson_details_for_student`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lesson` | string | Yes | Lesson ID/name |

**Response:**
```json
{
    "message": {
        "name": "lesson-12",
        "title": "Functions in Python",
        "chapter": "chapter-3",
        "chapter_title": "Functions",
        "course": "python-fundamentals",
        "number": "3-2",
        "body": "# Functions\n\nMarkdown content here...",
        "content": "{\"blocks\": [...]}",
        "youtube": "https://youtube.com/embed/xxx",
        "quiz_id": "quiz-functions",
        "has_assignment": true,
        "assignment_question": "Write a function that...",
        "file_type": "PDF",
        "is_complete": false,
        "is_enrolled": true,
        "prev_lesson": {
            "name": "lesson-11",
            "title": "Control Flow",
            "number": "3-1",
            "chapter": "chapter-3",
            "chapter_title": "Functions"
        },
        "next_lesson": {
            "name": "lesson-13",
            "title": "Lambda Functions",
            "number": "3-3",
            "chapter": "chapter-3",
            "chapter_title": "Functions"
        }
    }
}
```

**Note:** If user is not enrolled and lesson is not preview:
```json
{
    "message": {
        "name": "lesson-12",
        "title": "Functions in Python",
        "no_preview": true,
        "message": "Please enroll in this course to access this lesson"
    }
}
```

---

### Mark Lesson Complete

Mark a lesson as completed.

**Endpoint:** `POST /api/method/lms.lms.api.mark_lesson_progress`
**Auth Required:** Yes

**Request Body:**
```json
{
    "course": "python-fundamentals",
    "chapter_number": 3,
    "lesson_number": 2
}
```

**Response:**
```json
{
    "message": {
        "progress": 50.0
    }
}
```

---

## Quizzes API

### Get Quiz

Get quiz questions for taking.

**Endpoint:** `GET /api/method/lms.lms.api.get_lesson_quiz`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `quiz` | string | Yes | Quiz ID/name |

**Response:**
```json
{
    "message": {
        "name": "quiz-functions",
        "title": "Functions Quiz",
        "total_marks": 10,
        "passing_percentage": 70,
        "max_attempts": 3,
        "duration": "30",
        "show_answers": true,
        "shuffle_questions": true,
        "limit_questions_to": null,
        "show_submission_history": true,
        "attempts_made": 1,
        "can_attempt": true,
        "questions": [
            {
                "name": "question-1",
                "question": "<p>What keyword is used to define a function?</p>",
                "type": "Choices",
                "marks": 2,
                "multiple": false,
                "options": [
                    {"idx": 1, "option": "func"},
                    {"idx": 2, "option": "def"},
                    {"idx": 3, "option": "function"},
                    {"idx": 4, "option": "define"}
                ]
            },
            {
                "name": "question-2",
                "question": "<p>What does return statement do?</p>",
                "type": "Choices",
                "marks": 2,
                "multiple": false,
                "options": [...]
            }
        ]
    }
}
```

---

### Submit Quiz

Submit quiz answers.

**Endpoint:** `POST /api/method/lms.lms.api.submit_quiz_answers`
**Auth Required:** Yes

**Request Body:**
```json
{
    "quiz": "quiz-functions",
    "answers": [
        {"question": "question-1", "answer": ["2"]},
        {"question": "question-2", "answer": ["1"]},
        {"question": "question-3", "answer": ["3", "4"]}
    ]
}
```

**Response:**
```json
{
    "message": {
        "submission": "quiz-submission-001",
        "score": 8,
        "score_out_of": 10,
        "percentage": 80.0,
        "passing_percentage": 70,
        "passed": true,
        "is_open_ended": false
    }
}
```

---

### Get Quiz Result

Get detailed quiz result.

**Endpoint:** `GET /api/method/lms.lms.api.get_quiz_result`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `submission` | string | Yes | Submission ID |

**Response:**
```json
{
    "message": {
        "name": "quiz-submission-001",
        "quiz": "quiz-functions",
        "quiz_title": "Functions Quiz",
        "score": 8,
        "score_out_of": 10,
        "percentage": 80.0,
        "passing_percentage": 70,
        "passed": true,
        "submitted_on": "2024-01-20 15:30:00",
        "detailed_results": [
            {
                "question_name": "question-1",
                "question": "What keyword defines a function?",
                "answer": ["2"],
                "is_correct": 1,
                "marks": 2,
                "marks_out_of": 2
            }
        ]
    }
}
```

---

## Assignments API

### Get Course Assignments

Get all assignments for a course.

**Endpoint:** `GET /api/method/lms.lms.api.get_course_assignments`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `course` | string | Yes | Course ID/name |

**Response:**
```json
{
    "message": {
        "assignments": [
            {
                "name": "assignment-1",
                "title": "Build a Calculator",
                "type": "PDF",
                "question": "<p>Create a calculator program...</p>",
                "requires_grading": true,
                "submission": {
                    "name": "submission-001",
                    "status": "Pass",
                    "submitted_on": "2024-01-18",
                    "comments": "Great work!"
                }
            },
            {
                "name": "assignment-2",
                "title": "URL Submission",
                "type": "URL",
                "question": "<p>Submit your GitHub repo...</p>",
                "requires_grading": true,
                "submission": null
            }
        ]
    }
}
```

---

### Submit Assignment

Submit an assignment.

**Endpoint:** `POST /api/method/lms.lms.api.submit_assignment`
**Auth Required:** Yes

**Request Body (Text/URL type):**
```json
{
    "assignment": "assignment-2",
    "answer": "https://github.com/user/project"
}
```

**Request Body (File type):**
```json
{
    "assignment": "assignment-1",
    "attachment": "/files/my-submission.pdf"
}
```

**Response:**
```json
{
    "message": {
        "message": "Assignment submitted successfully",
        "submission": {
            "name": "submission-002",
            "assignment": "assignment-2",
            "status": "Not Graded",
            "submitted_on": "2024-01-20"
        }
    }
}
```

---

### Get Assignment Status

Get submission status and feedback.

**Endpoint:** `GET /api/method/lms.lms.api.get_assignment_status`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `submission` | string | Yes | Submission ID |

**Response:**
```json
{
    "message": {
        "name": "submission-001",
        "assignment": "assignment-1",
        "assignment_title": "Build a Calculator",
        "type": "PDF",
        "status": "Pass",
        "comments": "Excellent implementation! Good use of functions.",
        "evaluator": "Dr. Smith",
        "answer": null,
        "attachment": "/files/my-submission.pdf",
        "submitted_on": "2024-01-18 10:30:00"
    }
}
```

---

## Jobs API

### Get Job Opportunities

List available jobs (public endpoint).

**Endpoint:** `GET /api/method/lms.lms.api.get_job_opportunities`
**Auth Required:** No

**Response:**
```json
{
    "message": [
        {
            "name": "job-001",
            "job_title": "Python Developer",
            "location": "Remote",
            "country": "United States",
            "type": "Full Time",
            "work_mode": "Remote",
            "status": "Open",
            "company_name": "Tech Corp",
            "company_logo": "/files/techcorp.png"
        }
    ]
}
```

---

### Get Job Details

Get full job details (public endpoint).

**Endpoint:** `GET /api/method/lms.lms.api.get_job_details`
**Auth Required:** No

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job` | string | Yes | Job ID/name |

**Response:**
```json
{
    "message": {
        "name": "job-001",
        "job_title": "Python Developer",
        "location": "Remote",
        "country": "United States",
        "type": "Full Time",
        "work_mode": "Remote",
        "status": "Open",
        "description": "<p>Full job description...</p>",
        "company_name": "Tech Corp",
        "company_website": "https://techcorp.com",
        "company_logo": "/files/techcorp.png",
        "company_email_address": "hr@techcorp.com"
    }
}
```

---

### Apply for Job

Submit job application.

**Endpoint:** `POST /api/method/lms.lms.api.apply_for_job`
**Auth Required:** Yes

**Request Body:**
```json
{
    "job": "job-001",
    "resume": "/files/my-resume.pdf"
}
```

**Response:**
```json
{
    "message": {
        "message": "Application submitted successfully",
        "application": {
            "name": "application-001",
            "job": "job-001",
            "job_title": "Python Developer",
            "company": "Tech Corp",
            "applied_on": "2024-01-20"
        }
    }
}
```

---

### Get My Applications

List user's job applications.

**Endpoint:** `GET /api/method/lms.lms.api.get_my_applications`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start` | int | 0 | Pagination offset |
| `page_length` | int | 20 | Records per page |

**Response:**
```json
{
    "message": {
        "applications": [
            {
                "name": "application-001",
                "job": "job-001",
                "job_title": "Python Developer",
                "company": "Tech Corp",
                "resume": "/files/my-resume.pdf",
                "job_status": "Open",
                "applied_on": "2024-01-20"
            }
        ],
        "total_count": 3
    }
}
```

---

## Live Classes API

### Get Upcoming Live Classes

Get scheduled live classes.

**Endpoint:** `GET /api/method/lms.lms.api.get_my_live_classes`
**Auth Required:** Yes

**Response:**
```json
{
    "message": [
        {
            "name": "class-001",
            "title": "Python Advanced Topics",
            "date": "2024-01-25",
            "time": "14:00:00",
            "duration": 60,
            "batch_name": "batch-python-jan"
        }
    ]
}
```

---

### Get Live Class Details

Get class details with join URL.

**Endpoint:** `GET /api/method/lms.lms.api.get_live_class_details`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `live_class` | string | Yes | Class ID/name |

**Response:**
```json
{
    "message": {
        "name": "class-001",
        "title": "Python Advanced Topics",
        "description": "Deep dive into decorators...",
        "date": "2024-01-25",
        "time": "14:00:00",
        "duration": 60,
        "timezone": "Asia/Karachi",
        "host": "instructor@example.com",
        "host_name": "Dr. Smith",
        "batch": "batch-python-jan",
        "batch_title": "Python January Batch",
        "join_url": "https://zoom.us/j/123456789",
        "password": "abc123",
        "is_upcoming": true,
        "can_join": true,
        "has_recording": true
    }
}
```

**Note:** `join_url` and `password` are only provided when `can_join` is true (15 minutes before class starts).

---

## Certificates API

### Get My Certificates

List earned certificates.

**Endpoint:** `GET /api/method/lms.lms.api.get_my_certificates`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start` | int | 0 | Pagination offset |
| `page_length` | int | 20 | Records per page |

**Response:**
```json
{
    "message": {
        "certificates": [
            {
                "name": "cert-001",
                "course": "python-fundamentals",
                "course_title": "Python Fundamentals",
                "batch_name": null,
                "batch_title": null,
                "issue_date": "2024-01-15",
                "expiry_date": null,
                "template": "Standard Certificate",
                "published": 1,
                "download_url": "/api/method/frappe.utils.print_format.download_pdf?..."
            }
        ],
        "total_count": 2
    }
}
```

---

### Get Certificate Details

Get certificate with download URL.

**Endpoint:** `GET /api/method/lms.lms.api.get_certificate_details`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `certificate` | string | Yes | Certificate ID |

**Response:**
```json
{
    "message": {
        "name": "cert-001",
        "member": "student@example.com",
        "member_name": "John Doe",
        "course": "python-fundamentals",
        "course_title": "Python Fundamentals",
        "batch_name": null,
        "batch_title": null,
        "issue_date": "2024-01-15",
        "expiry_date": null,
        "template": "Standard Certificate",
        "evaluator": null,
        "evaluator_name": null,
        "published": 1,
        "download_url": "/api/method/frappe.utils.print_format.download_pdf?doctype=LMS%20Certificate&name=cert-001&format=Standard%20Certificate"
    }
}
```

---

## Profile API

### Update Profile

Update user profile.

**Endpoint:** `POST /api/method/lms.lms.api.update_profile`
**Auth Required:** Yes

**Request Body:**
```json
{
    "full_name": "John Doe",
    "bio": "Software developer passionate about Python",
    "headline": "Learning enthusiast",
    "user_image": "/files/new-profile.jpg",
    "linkedin": "https://linkedin.com/in/johndoe",
    "github": "https://github.com/johndoe",
    "twitter": "johndoe"
}
```

All fields are optional. Only provided fields will be updated.

**Response:**
```json
{
    "message": {
        "message": "Profile updated successfully",
        "profile": {
            "name": "student@example.com",
            "email": "student@example.com",
            "full_name": "John Doe",
            "username": "johndoe",
            "user_image": "/files/new-profile.jpg",
            "bio": "Software developer passionate about Python",
            "headline": "Learning enthusiast",
            "linkedin": "https://linkedin.com/in/johndoe",
            "github": "https://github.com/johndoe",
            "twitter": "johndoe"
        }
    }
}
```

---

### Change Password

Change user password.

**Endpoint:** `POST /api/method/lms.lms.api.change_password`
**Auth Required:** Yes

**Request Body:**
```json
{
    "old_password": "currentpassword",
    "new_password": "newpassword123"
}
```

**Response:**
```json
{
    "message": {
        "message": "Password changed successfully"
    }
}
```

**Validation:**
- New password minimum 6 characters
- Old password must be correct

---

## Notifications API

### Get Notifications

Get user notifications.

**Endpoint:** `GET /api/method/lms.lms.api.get_notifications`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filters` | JSON | No | Filter criteria |

**Response:**
```json
{
    "message": [
        {
            "name": "notification-001",
            "subject": "New lesson available",
            "message": "A new lesson has been added...",
            "read": 0,
            "creation": "2024-01-20 10:00:00"
        }
    ]
}
```

---

### Mark as Read

Mark notification as read.

**Endpoint:** `POST /api/method/lms.lms.api.mark_as_read`
**Auth Required:** Yes

**Request Body:**
```json
{
    "name": "notification-001"
}
```

---

### Mark All as Read

Mark all notifications as read.

**Endpoint:** `POST /api/method/lms.lms.api.mark_all_as_read`
**Auth Required:** Yes

---

## Batch API

### Get My Batches

List enrolled batches.

**Endpoint:** `GET /api/method/lms.lms.api.get_my_batches`
**Auth Required:** Yes

**Response:**
```json
{
    "message": [
        {
            "name": "batch-python-jan",
            "title": "Python January Batch",
            "start_date": "2024-01-01",
            "end_date": "2024-03-31"
        }
    ]
}
```

---

### Get My Batch

Get batch details for enrolled student.

**Endpoint:** `GET /api/method/lms.lms.api.get_my_batch`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `batch` | string | Yes | Batch ID/name |

**Response:**
```json
{
    "message": {
        "name": "batch-python-jan",
        "title": "Python January Batch",
        "description": "Comprehensive Python training",
        "batch_details": "<p>Full details...</p>",
        "start_date": "2024-01-01",
        "end_date": "2024-03-31",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "timezone": "Asia/Karachi",
        "certification": true,
        "medium": "Online",
        "category": "Programming",
        "courses": [
            {
                "name": "python-fundamentals",
                "title": "Python Fundamentals",
                "image": "/files/python.jpg",
                "short_introduction": "Learn Python basics",
                "lessons": 24
            }
        ],
        "instructors": [
            {
                "name": "instructor@example.com",
                "full_name": "Dr. Smith",
                "user_image": "/files/smith.jpg"
            }
        ],
        "enrollment": {
            "name": "enrollment-001",
            "status": "Active",
            "access_start_date": "2024-01-01",
            "access_end_date": "2024-06-30",
            "is_time_limited": true,
            "enrollment_date": "2024-01-01"
        }
    }
}
```

---

### Get Batch Timetable

Get batch schedule.

**Endpoint:** `GET /api/method/lms.lms.api.get_batch_timetable`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `batch` | string | Yes | Batch ID/name |
| `date` | string | No | Filter by specific date (YYYY-MM-DD) |

**Response:**
```json
{
    "message": {
        "batch": "batch-python-jan",
        "timetable": [
            {
                "date": "2024-01-25",
                "day": "Thursday",
                "entries": [
                    {
                        "start_time": "09:00:00",
                        "end_time": "10:30:00",
                        "duration": "1h 30m",
                        "reference_doctype": "Course Lesson",
                        "reference_docname": "lesson-functions",
                        "title": "Functions in Python",
                        "milestone": false
                    },
                    {
                        "start_time": "14:00:00",
                        "end_time": "15:00:00",
                        "duration": "1h",
                        "reference_doctype": "LMS Live Class",
                        "reference_docname": "class-001",
                        "title": "Live Q&A Session",
                        "milestone": false
                    }
                ]
            }
        ],
        "legends": [
            {"legend": "Lecture", "color": "#4CAF50"},
            {"legend": "Live Class", "color": "#2196F3"}
        ]
    }
}
```

---

## Dashboard API

### Get Learning Stats

Get aggregated statistics for dashboard.

**Endpoint:** `GET /api/method/lms.lms.api.get_learning_stats`
**Auth Required:** Yes

**Response:**
```json
{
    "message": {
        "enrolled_courses": 5,
        "completed_courses": 2,
        "in_progress_courses": 3,
        "total_lessons_completed": 45,
        "total_quizzes_passed": 12,
        "total_assignments_submitted": 8,
        "certificates_earned": 2,
        "current_streak": 7,
        "longest_streak": 15,
        "badges": 3,
        "upcoming_live_classes": 2,
        "recent_activity": [
            {
                "type": "lesson_completed",
                "title": "Completed: Functions in Python",
                "course": "Python Fundamentals",
                "timestamp": "2024-01-20 14:30:00"
            }
        ]
    }
}
```

---

### Get My Badges

Get earned badges.

**Endpoint:** `GET /api/method/lms.lms.api.get_assigned_badges`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `member` | string | No | User email (defaults to current user) |

---

## Discussions API

### Get Lesson Discussions

Get Q&A for a lesson.

**Endpoint:** `GET /api/method/lms.lms.api.get_lesson_discussions`
**Auth Required:** Yes

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lesson` | string | Yes | Lesson ID/name |
| `start` | int | No | Pagination offset (default: 0) |
| `page_length` | int | No | Records per page (default: 20) |

**Response:**
```json
{
    "message": {
        "discussions": [
            {
                "name": "comment-001",
                "content": "Can you explain decorators more?",
                "author_name": "Jane Smith",
                "author_image": "/files/jane.jpg",
                "created_on": "2024-01-20 10:30:00",
                "modified": "2024-01-20 10:30:00",
                "reply_count": 2
            }
        ],
        "total_count": 15
    }
}
```

---

### Post Discussion

Post a new question.

**Endpoint:** `POST /api/method/lms.lms.api.post_discussion`
**Auth Required:** Yes

**Request Body:**
```json
{
    "lesson": "lesson-functions",
    "content": "I have a question about lambda functions..."
}
```

**Response:**
```json
{
    "message": {
        "message": "Discussion posted successfully",
        "discussion": {
            "name": "comment-002",
            "content": "I have a question about lambda functions...",
            "author_name": "John Doe",
            "author_image": "/files/john.jpg",
            "created_on": "2024-01-20 15:00:00"
        }
    }
}
```

---

### Post Reply

Reply to a discussion.

**Endpoint:** `POST /api/method/lms.lms.api.post_reply`
**Auth Required:** Yes

**Request Body:**
```json
{
    "comment": "comment-001",
    "content": "Lambda functions are anonymous functions..."
}
```

**Response:**
```json
{
    "message": {
        "message": "Reply posted successfully",
        "reply": {
            "name": "comment-003",
            "content": "Lambda functions are anonymous functions...",
            "author_name": "Dr. Smith",
            "author_image": "/files/smith.jpg",
            "created_on": "2024-01-20 15:30:00"
        }
    }
}
```

---

## Error Handling

### Error Response Format

```json
{
    "exc_type": "ValidationError",
    "exception": "frappe.exceptions.ValidationError: Course is required",
    "_error_message": "Course is required",
    "_server_messages": "[\"Course is required\"]"
}
```

### HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| 200 | Success | Request completed successfully |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | User lacks permission |
| 404 | Not Found | Resource doesn't exist |
| 417 | Expectation Failed | Validation error |
| 500 | Server Error | Server-side exception |

### Common Errors

**Authentication Error:**
```json
{
    "exc_type": "AuthenticationError",
    "_error_message": "Invalid email or password"
}
```

**Validation Error:**
```json
{
    "exc_type": "ValidationError",
    "_error_message": "Course is required"
}
```

**Permission Error:**
```json
{
    "exc_type": "PermissionError",
    "_error_message": "You are not enrolled in this course"
}
```

**Not Found Error:**
```json
{
    "exc_type": "DoesNotExistError",
    "_error_message": "Lesson not found"
}
```

---

## Rate Limits

- **Signup:** Maximum 300 requests per 60 seconds
- **General API:** No specific limit (depends on server configuration)

---

## Changelog

### Version 1.0 (Initial Release)
- 36 API endpoints for student mobile app
- Token-based authentication
- Full course, lesson, quiz, assignment support
- Jobs, certificates, notifications
- Batch management with timetables
- Discussion/Q&A system
