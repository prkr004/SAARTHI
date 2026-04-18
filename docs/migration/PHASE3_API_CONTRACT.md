# Phase 3 API Contracts (Chat + RAG + Temporal)

## Final Endpoint List

### Auth

- POST `/api/v1/auth/register`
- POST `/api/v1/auth/login`
- GET `/api/v1/auth/me`
- POST `/api/v1/auth/logout`

### Admin (Phase 6 extension)

- GET `/api/v1/admin/users/pending`
- GET `/api/v1/admin/users/history`
- POST `/api/v1/admin/users/{user_id}/approve`
- POST `/api/v1/admin/users/{user_id}/reject`
- POST `/api/v1/admin/ingestion/jobs` (multipart PDF upload)
- GET `/api/v1/admin/ingestion/jobs/{job_id}`
- GET `/api/v1/admin/ingestion/jobs?limit={n}`

### Conversations and Messages

- GET `/api/v1/conversations`
- POST `/api/v1/conversations`
- POST `/api/v1/conversations/default`
- PATCH `/api/v1/conversations/{conversation_id}`
- DELETE `/api/v1/conversations/{conversation_id}`
- GET `/api/v1/conversations/{conversation_id}/messages`
- POST `/api/v1/conversations/{conversation_id}/messages`

### RAG and Temporal

- GET `/api/v1/models`
- POST `/api/v1/chat/ask`
- POST `/api/v1/chat/ask-temporal`

## Response Envelope (Phase 3)

Used by `/api/v1/models`, `/api/v1/chat/ask`, `/api/v1/chat/ask-temporal`:

```json
{
  "success": true,
  "request_id": "3b2ca6fd-9f6d-4f34-a8c8-b8af7d7f5c5f",
  "timestamp": "2026-04-07T13:00:00.000000+00:00",
  "data": {},
  "error": null
}
```

Error envelope example:

```json
{
  "success": false,
  "request_id": "3b2ca6fd-9f6d-4f34-a8c8-b8af7d7f5c5f",
  "timestamp": "2026-04-07T13:00:00.000000+00:00",
  "data": null,
  "error": {
    "code": "model_unavailable",
    "message": "Could not connect to local model service.",
    "details": {
      "reason": "..."
    }
  }
}
```

## Sample Payloads

### 1) QA Request

POST `/api/v1/chat/ask`

```json
{
  "question": "What are key KYC requirements?",
  "model_id": "phi:2.7b",
  "top_k": 4
}
```

Success response (trimmed):

```json
{
  "success": true,
  "request_id": "...",
  "timestamp": "...",
  "data": {
    "mode": "qa",
    "answer": "...",
    "sources": [
      {
        "content": "...",
        "metadata": {
          "source": "...",
          "page": 12
        }
      }
    ],
    "formatted_sources": [
      {
        "document_name": "RBI Master Direction on KYC",
        "document_link": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
        "page": 12,
        "snippet": "...",
        "metadata": {
          "source": "...",
          "page": 12
        }
      }
    ],
    "metadata": {
      "predefined": false,
      "top_k": 4,
      "model_id": "phi:2.7b",
      "elapsed_ms": 230
    }
  },
  "error": null
}
```

### 2) Temporal Request

POST `/api/v1/chat/ask-temporal`

```json
{
  "question": "How has digital lending guidance changed?",
  "model_id": "phi:2.7b",
  "top_k": 5,
  "comparison_method": "both"
}
```

Success response (comparison path, trimmed):

```json
{
  "success": true,
  "request_id": "...",
  "timestamp": "...",
  "data": {
    "mode": "temporal_comparison",
    "answer": "...",
    "sources": [],
    "formatted_sources": [],
    "temporal": {
      "intent_detected": true,
      "executed": true,
      "fallback": false,
      "fallback_reason": null,
      "single_version": false,
      "document_title": "...",
      "current_date": "...",
      "previous_date": "...",
      "comparison": {
        "difflib_result": "...",
        "llm_summary": "..."
      }
    },
    "metadata": {
      "predefined": false,
      "top_k": 5,
      "model_id": "phi:2.7b",
      "comparison_method": "both",
      "elapsed_ms": 780
    }
  },
  "error": null
}
```

## Error Mapping

- `validation_error` -> 400
- `vector_index_missing` -> 503
- `model_unavailable` -> 503
- `request_timeout` -> 504
- `internal_error` -> 500

## Auth Contract Updates (Phase 6 extension)

- Registration now returns pending-approval message on success:
  - `Your request has been sent to the admin. Once approved, you will have access to SAARTHI!`
- Login rejects pending/rejected users with `403` and clear detail text.
- `/api/v1/auth/me` now includes:
  - `role`: `admin | user`
  - `approval_status`: `pending | approved | rejected`
  - `email`: optional

## Admin API Contract Notes

### Approve user

POST `/api/v1/admin/users/{user_id}/approve`

Request body:

```json
{
  "review_reason": "Verified onboarding details"
}
```

Response shape:

```json
{
  "message": "User approved successfully.",
  "user": {
    "id": 27,
    "employee_id": "EMP8123",
    "full_name": "Aman Sharma",
    "email": "aman@example.com",
    "role": "user",
    "approval_status": "approved",
    "created_at": "2026-04-19T10:00:00+00:00",
    "reviewed_by": 1,
    "reviewed_at": "2026-04-19T10:03:00+00:00",
    "review_reason": "Verified onboarding details",
    "reviewer_employee_id": "ADMIN001",
    "reviewer_name": "Bank Admin"
  },
  "warning": null
}
```

### Create ingestion job

POST `/api/v1/admin/ingestion/jobs` with form field `files` (multiple PDFs).

Response shape:

```json
{
  "message": "Ingestion job created.",
  "job": {
    "job_id": "RANDOM_JOB_ID",
    "status": "queued",
    "total_files": 3,
    "processed_files": 0,
    "total_chunks": 0,
    "progress_percent": 0,
    "current_file": null,
    "error_message": null
  }
}
```

### Poll ingestion job

GET `/api/v1/admin/ingestion/jobs/{job_id}` returns status transitions:

- `queued` -> `running` -> `completed`
- `queued` -> `running` -> `failed`

## Verification Checklist for Phase 4 Frontend

- Verify auth token is sent as `Authorization: Bearer <token>` on all protected endpoints.
- Read and display `X-Request-Id` from response headers for debugging support links.
- Handle envelope success branch via `success=true` and consume `data` object.
- Handle envelope error branch via `success=false` and show `error.message`.
- For QA endpoint, render `formatted_sources` and support fallback if raw `sources` are empty.
- For temporal endpoint, branch UI by `data.mode`:
  - `temporal_comparison`
  - `temporal_fallback`
  - `temporal_single_version`
  - `qa_fallback_non_temporal`
  - `predefined`
- Render temporal metadata panel from `data.temporal`.
- Add timeout UX for 504 responses and retry action.
- Add user guidance for 503 `model_unavailable` and `vector_index_missing`.
- Confirm model selector pulls from GET `/api/v1/models` and defaults to `recommended_model`.
