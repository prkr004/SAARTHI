# SAARTHI API Backend

FastAPI backend for auth, chat history, model metadata, RAG Q&A, and temporal compare flows.

## Local Run

```powershell
cd "C:\4th Year\cap_trial"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Open docs:
- http://localhost:8000/docs

Health endpoints:
- http://localhost:8000/api/v1/health/live
- http://localhost:8000/api/v1/health/ready

## Environment Setup

```powershell
cd "C:\4th Year\cap_trial"
Copy-Item .env.example .env
```

Important runtime controls:
- SAARTHI_LOG_FORMAT=text|json
- SAARTHI_SESSION_MAX_ACTIVE_PER_USER
- SAARTHI_READINESS_REQUIRE_VECTOR_INDEX
- SAARTHI_CORS_ALLOWED_ORIGINS
- SAARTHI_TRUSTED_HOSTS

## API Surface

Auth:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/me
- POST /api/v1/auth/logout

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
cd "C:\4th Year\cap_trial"
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

## Profiling Command

```powershell
cd "C:\4th Year\cap_trial"
.\.venv\Scripts\python.exe backend/scripts/profile_phase5.py
```

## Troubleshooting

- request_timeout errors:
  - Increase timeout env values only after model/runtime checks.
- model_unavailable errors:
  - Ensure Ollama is running and target model is pulled.
- readiness failures:
  - Verify DB path and optional vector index path.

## Related Documents

- ../docs/migration/PHASE3_API_CONTRACT.md
- ../docs/phase/PHASE5_PRODUCTION_READINESS_REPORT.md
- ../docs/phase/PHASE5_RESIDUAL_RISKS.md
- ../docs/phase/PHASE5_POST_LAUNCH_MONITORING_CHECKLIST.md
