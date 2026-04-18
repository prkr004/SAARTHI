# SAARTHI API Backend

FastAPI backend for auth, chat history, model metadata, RAG Q&A, and temporal compare flows.

## Local Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000
```

Open docs:
- http://localhost:8000/docs

Health endpoints:
- http://localhost:8000/api/v1/health/live
- http://localhost:8000/api/v1/health/ready

## Environment Setup

```powershell
Copy-Item .env.example .env
```

Important runtime controls:
- SAARTHI_LOG_FORMAT=text|json
- SAARTHI_SESSION_MAX_ACTIVE_PER_USER
- SAARTHI_READINESS_REQUIRE_VECTOR_INDEX
- SAARTHI_CORS_ALLOWED_ORIGINS
- SAARTHI_TRUSTED_HOSTS
- SAARTHI_ADMIN_EMPLOYEE_ID
- SAARTHI_ADMIN_NAME
- SAARTHI_ADMIN_PASSWORD
- SAARTHI_ADMIN_EMAIL
- SAARTHI_NOTIFICATION_PROVIDER=noop|console|smtp
- SAARTHI_NOTIFICATION_FROM_EMAIL
- SAARTHI_NOTIFICATION_SMTP_HOST
- SAARTHI_NOTIFICATION_SMTP_PORT
- SAARTHI_NOTIFICATION_SMTP_USERNAME
- SAARTHI_NOTIFICATION_SMTP_PASSWORD
- SAARTHI_NOTIFICATION_SMTP_USE_SSL
- SAARTHI_NOTIFICATION_SMTP_USE_STARTTLS
- SAARTHI_ADMIN_UPLOAD_DIRECTORY
- SAARTHI_ADMIN_UPLOAD_MAX_FILES_PER_JOB
- SAARTHI_ADMIN_UPLOAD_MAX_FILE_SIZE_MB

## API Surface

Auth:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/me
- POST /api/v1/auth/logout

Admin:
- GET /api/v1/admin/users/pending
- GET /api/v1/admin/users/history
- POST /api/v1/admin/users/{user_id}/approve
- POST /api/v1/admin/users/{user_id}/reject
- POST /api/v1/admin/ingestion/jobs
- GET /api/v1/admin/ingestion/jobs/{job_id}
- GET /api/v1/admin/ingestion/jobs

Conversations:
- GET /api/v1/conversations
- POST /api/v1/conversations
- POST /api/v1/conversations/default
- PATCH /api/v1/conversations/{conversation_id}
- DELETE /api/v1/conversations/{conversation_id}
- GET /api/v1/conversations/{conversation_id}/messages
- POST /api/v1/conversations/{conversation_id}/messages

RAG and Temporal:
- GET /api/v1/models
- POST /api/v1/chat/ask
- POST /api/v1/chat/ask-temporal

## Test Commands

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

## Profiling Command

```powershell
.\.venv\Scripts\python.exe backend/scripts/profile_phase5.py
```

## Troubleshooting

- request_timeout errors:
  - Increase timeout env values only after model/runtime checks.
- model_unavailable errors:
  - Ensure Ollama is running and target model is pulled.
- readiness failures:
  - Verify DB path and optional vector index path.

## Admin Notes

- New registrations are created in `pending` state by default.
- Pending and rejected users cannot log in until an admin updates review status.
- Bootstrap admin user is always forced to role `admin` and approval status `approved` at startup.
- Upload ingestion enforces PDF extension/content-type/size checks and updates a persistent progress job.
- If email delivery fails, approval/rejection still succeeds and the API response includes a warning.

## Related Documents

- ../docs/migration/PHASE3_API_CONTRACT.md
- ../docs/phase/PHASE5_PRODUCTION_READINESS_REPORT.md
- ../docs/phase/PHASE5_RESIDUAL_RISKS.md
- ../docs/phase/PHASE5_POST_LAUNCH_MONITORING_CHECKLIST.md
