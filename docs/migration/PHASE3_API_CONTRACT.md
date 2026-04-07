# Phase 3 API Contracts (Chat + RAG + Temporal)

## Final Endpoint List

### Auth

- POST `/api/v1/auth/register`
- POST `/api/v1/auth/login`
- GET `/api/v1/auth/me`
- POST `/api/v1/auth/logout`

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
