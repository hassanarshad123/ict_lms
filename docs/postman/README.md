# LMS Student Mobile App API Documentation

This documentation covers all API endpoints available for the React Native student mobile app.

## Quick Start

### 1. Import Postman Collection

Import `LMS_Student_Mobile_API.postman_collection.json` into Postman.

### 2. Set Environment Variables

Create a Postman environment with these variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `base_url` | Your LMS instance URL | `https://your-lms.frappe.cloud` |
| `api_key` | API key from login | (auto-filled after login) |
| `api_secret` | API secret from login | (auto-filled after login) |

### 3. Authenticate

Call the **Login** endpoint first to get your API credentials.

---

## Authentication

All authenticated endpoints require the `Authorization` header:

```
Authorization: token <api_key>:<api_secret>
```

### Login Flow

```http
POST /api/method/lms.lms.api.api_login
Content-Type: application/json

{
    "usr": "student@example.com",
    "pwd": "password123"
}
```

**Response:**
```json
{
    "message": "Login successful",
    "api_key": "abc123def456",
    "api_secret": "xyz789ghi012",
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
```

Store `api_key` and `api_secret` securely in the app.

---

## API Endpoints Summary

### Authentication (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `api_login` | POST | No | Login with credentials |
| `api_sign_up` | POST | No | Register new student |
| `get_user_info` | GET | Yes | Get current user info |

### Courses (4 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_enrolled_courses` | GET | Yes | List enrolled courses |
| `get_course_details_for_student` | GET | Yes | Get course details |
| `get_course_progress` | GET | Yes | Get detailed progress |
| `get_course_outline_for_student` | GET | Yes | Get chapters & lessons |

### Lessons (2 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_lesson_details_for_student` | GET | Yes | Get lesson content |
| `mark_lesson_progress` | POST | Yes | Mark lesson complete |

### Quizzes (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_lesson_quiz` | GET | Yes | Get quiz questions |
| `submit_quiz_answers` | POST | Yes | Submit answers |
| `get_quiz_result` | GET | Yes | Get quiz result |

### Assignments (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_course_assignments` | GET | Yes | List assignments |
| `submit_assignment` | POST | Yes | Submit assignment |
| `get_assignment_status` | GET | Yes | Get submission status |

### Jobs (4 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_job_opportunities` | GET | No | List job openings |
| `get_job_details` | GET | No | Get job details |
| `apply_for_job` | POST | Yes | Apply for job |
| `get_my_applications` | GET | Yes | List my applications |

### Live Classes (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_my_live_classes` | GET | Yes | Upcoming classes |
| `get_live_class_details` | GET | Yes | Get class with join URL |
| `get_course_recordings` | GET | Yes | Past recordings |

### Certificates (2 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_my_certificates` | GET | Yes | List certificates |
| `get_certificate_details` | GET | Yes | Get with download URL |

### Profile (2 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `update_profile` | POST | Yes | Update profile |
| `change_password` | POST | Yes | Change password |

### Notifications (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_notifications` | GET | Yes | List notifications |
| `mark_as_read` | POST | Yes | Mark one as read |
| `mark_all_as_read` | POST | Yes | Mark all as read |

### Batch (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_my_batches` | GET | Yes | List enrolled batches |
| `get_my_batch` | GET | Yes | Get batch details |
| `get_batch_timetable` | GET | Yes | Get timetable |

### Dashboard (2 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_learning_stats` | GET | Yes | Dashboard statistics |
| `get_assigned_badges` | GET | Yes | User badges |

### Discussions (3 endpoints)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `get_lesson_discussions` | GET | Yes | Lesson Q&A |
| `post_discussion` | POST | Yes | Post question |
| `post_reply` | POST | Yes | Reply to question |

---

## Common Response Patterns

### Success Response
```json
{
    "message": {
        "courses": [...],
        "total_count": 10
    }
}
```

### Error Response
```json
{
    "exc_type": "ValidationError",
    "exception": "frappe.exceptions.ValidationError: Course is required",
    "_error_message": "Course is required"
}
```

### Pagination
Most list endpoints support pagination:
- `start` - Offset (default: 0)
- `page_length` - Records per page (default: 20)

---

## Error Codes

| HTTP Code | Meaning |
|-----------|---------|
| 200 | Success |
| 401 | Unauthorized (invalid/missing token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 417 | Validation error |
| 500 | Server error |

---

## Mobile App Integration Tips

### Secure Token Storage
- iOS: Use Keychain Services
- Android: Use EncryptedSharedPreferences or Keystore

### Token Refresh
The API secret is regenerated on each login. If you receive a 401 error:
1. Clear stored credentials
2. Prompt user to login again
3. Store new credentials

### Offline Support
Cache these endpoints for offline viewing:
- `get_enrolled_courses`
- `get_course_outline_for_student`
- `get_lesson_details_for_student` (lesson content)

### File Uploads
For assignment submissions with files:
1. First upload file using Frappe's file upload API
2. Then submit assignment with the file path

```http
POST /api/method/upload_file
Content-Type: multipart/form-data

file: <binary>
```

---

## CORS Configuration

If testing from a different domain, ensure CORS is configured on the server:

```python
# In site_config.json
{
    "allow_cors": "*"
}
```

Or for specific domains:
```python
{
    "allow_cors": ["https://your-mobile-app.com"]
}
```

---

## Support

For issues or questions about the API, contact the development team.
