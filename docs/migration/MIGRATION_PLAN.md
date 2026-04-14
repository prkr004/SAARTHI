# SAARTHI React + FastAPI Migration Plan

## 1. Repo Audit

Current state and reusable modules:

- UI and chat orchestration: `app.py` (Streamlit)
- Retrieval and temporal RAG logic: `query.py`
- Auth and persistence: `chat_store.py`
- Temporal intent/comparison: `temporal/intent_detector.py`, `temporal/comparator.py`
- Model catalog and defaults: `models_config.py`

Key migration decision:

- Keep Streamlit operational as fallback.
- Build API + React in parallel inside this repository.
- Reuse Python domain logic first, then refine internals after parity.

## 2. Proposed API Contract

Phase 1 (implemented):

- POST `/api/v1/auth/register`
  - Request: `employee_id`, `full_name`, `password`
  - Response: success message
- POST `/api/v1/auth/login`
  - Request: `employee_id`, `password`
  - Response: `access_token`, `token_type`, `expires_at`, `user`
- GET `/api/v1/auth/me`
  - Header: `Authorization: Bearer <token>`
  - Response: authenticated user profile
- POST `/api/v1/auth/logout`
  - Header: `Authorization: Bearer <token>`
  - Response: success message
- GET `/api/v1/health/live`
- GET `/api/v1/health/ready`

Phase 2 (implemented):

- GET `/api/v1/conversations`
- POST `/api/v1/conversations`
- POST `/api/v1/conversations/default`
- PATCH `/api/v1/conversations/{conversation_id}`
- DELETE `/api/v1/conversations/{conversation_id}`
- GET `/api/v1/conversations/{conversation_id}/messages`
- POST `/api/v1/conversations/{conversation_id}/messages`

Phase 3 (implemented):

- GET `/api/v1/models`
- POST `/api/v1/chat/ask`
- POST `/api/v1/chat/ask-temporal`

## 3. Exact Folder Structure

```text
backend/
  app/
    main.py
    api/
      deps.py
      routers/
        auth.py
        chat.py
        health.py
    core/
      config.py
      logging_config.py
    schemas/
      auth.py
      chat.py
      common.py
    services/
      auth_service.py
  tests/
    test_auth_api.py
    test_chat_api.py
  README.md
```

Planned additions by later phases:

```text
frontend/
  src/
    app/
    features/auth/
    features/chat/
    features/models/
    components/
    lib/api/
```

## 4. Data Model Mapping

Existing tables reused:

- `users` (employee auth)
- `conversations`
- `messages`

Phase 1 additions:

- `api_sessions`
  - `token_hash` (PK)
  - `user_id` (FK -> users.id)
  - `created_at`, `expires_at`, `revoked_at`
  - `user_agent`

Domain mapping:

- Streamlit session state -> API bearer session token
- Existing `AuthResult` from `chat_store.py` -> `UserProfile` + token response

## 5. Risk Register And Mitigation

1. Risk: Session/auth regressions during transition.
- Mitigation: keep Streamlit login flow unchanged, isolate API auth in new router/service, add auth tests.

2. Risk: DB compatibility issues.
- Mitigation: additive schema only (`api_sessions`), no destructive migration.

3. Risk: Frontend/API contract drift.
- Mitigation: typed schemas, explicit contracts in this plan, add integration tests in Phase 4.

4. Risk: Python 3.14 ecosystem compatibility warning (LangChain/Pydantic v1 compatibility).
- Mitigation: prefer Python 3.12 for migration runtime and CI.

5. Risk: Parallel app confusion for team members.
- Mitigation: separate run docs for Streamlit and API, phase-by-phase checklists.

## 6. Rollback Strategy

- No replacement-in-place during early phases.
- If API issues occur, stop FastAPI process and continue running Streamlit only.
- Since schema change is additive, existing app remains unaffected.
- Defer Streamlit retirement until parity checklist is fully green.

## 7. Phase Status

Phase 1 complete:

- FastAPI scaffold with versioned routing and CORS.
- Auth endpoints (`register`, `login`, `me`, `logout`).
- Session tokens with DB-backed revocation.
- Health endpoints.
- Automated auth API tests.

Phase 2 complete:

- Conversation APIs for list/create/rename/delete/default-conversation.
- Message APIs for list/add with role-restricted payload validation.
- Strict ownership enforcement with explicit 403 responses.
- Integration tests covering happy paths and negative permission cases.

Phase 3 complete:

- Model catalog endpoint for frontend model selection.
- Unified envelope responses for QA and temporal APIs.
- Predefined response integration before RAG execution.
- Temporal intent detection and structured temporal output paths.
- Timeout guards, request tracing id support, and consistent error mapping.
- Regression tests for normal, fallback, and error paths.

Next: Phase 4 (React feature parity frontend).

Phase 4 complete:

- React + TypeScript frontend scaffolded via Vite.
- Router and guarded auth flows implemented (login/register/logout/protected workspace).
- Chat workspace implemented with conversation CRUD, message history, ask flow, source rendering, and model persistence.
- Unified API client integration for Phase 2 and Phase 3 endpoints with retry + timeout handling.
- Responsive UI system and accessible interaction patterns added.
- Frontend tests added for auth, conversation actions, and ask flow.

Next: Phase 5 (hardening, deployment readiness, QA expansion).

Phase 5 complete:

- Security and robustness hardening applied (session cap, sanitization, CORS/trusted-host validation, environment templates).
- Reliability upgrades shipped (structured logging mode, request tracing logs, stronger readiness checks, graceful unhandled error response).
- Performance optimizations implemented and benchmarked (conversation query optimization and source formatting cache).
- Test coverage expanded with Phase 5 hardening + end-to-end API smoke journey.
- Developer experience improved with one-command local startup scripts for backend/frontend and updated runbooks.
- Deployment/cutover documentation delivered with go-live criteria, rollback strategy, residual risks, and monitoring checklist.

## 8. Phase 1 Delta (2026-04-14) - Corpus Manifest Onboarding

- Replaced hardcoded corpus configuration in `build_vectorstore.py` with manifest-driven onboarding.
- Added strict manifest validation for required metadata keys: `regulator`, `document_title`, `version_date`, `effective_date`, and `amends` (nullable key).
- Introduced `data/corpus_manifest.json` as the default corpus source of truth.
- Included RBI + SEBI + DPDP sources from `data/` in the default manifest.
- Preserved index output path defaults (`faiss_index`) and runtime readiness assumptions.
- Preserved backward compatibility for existing indexed chunks by keeping chunk metadata parsing tolerant for older metadata.

## 9. Phase 2 Delta (2026-04-14) - Hybrid Retrieval Layer

- Added hybrid retrieval in `query.py` that merges FAISS vector relevance and keyword overlap relevance with weighted ranking.
- Kept FAISS retrieval as the base path and layered keyword scoring over indexed chunk content + metadata.
- Introduced configurable hybrid controls via backend settings:
  - `hybrid_vector_weight`
  - `hybrid_keyword_weight`
  - `hybrid_candidate_multiplier`
  - `hybrid_keyword_min_token_length`
- Preserved existing response envelope and payload keys for `/api/v1/chat/ask` and `/api/v1/chat/ask-temporal`.
- Added deterministic tests for hybrid ranking behavior and response-shape stability in `backend/tests/test_rag_api.py`.

## 10. Phase 3 Delta (2026-04-14) - Intent Triage Routing

- Upgraded intent logic from binary temporal detection to triage classes in `temporal/intent_detector.py`:
  - `fact_retrieval`
  - `timeline_analysis`
  - `drafting_request`
- Integrated class-based routing in `/api/v1/chat/ask-temporal`:
  - fact -> QA fallback path
  - timeline -> temporal comparison path
  - drafting -> drafting pipeline entrypoint stub
- Preserved response envelope shape and existing keys while adding `intent_class` visibility in payload metadata/temporal blocks.
- Retained `detect_temporal_intent()` as a backward-compatible wrapper for legacy callers.
- Extended tests for all three classes plus fallback behavior in `backend/tests/test_rag_api.py`.

## 11. Phase 4 Delta (2026-04-14) - Semantic Circular Linking

- Added a new metadata-graph resolver service: `backend/app/services/circular_linking_service.py`.
- Built relation graph edges from indexed metadata for:
  - amendment links (`amends` / `amended_by`)
  - parent-child circular hierarchy (`parent_child`) via title containment and token overlap.
- Integrated circular-linking output into query paths (`ask_question` and `ask_temporal_question`) with additive optional payload only.
- Preserved backward compatibility of API envelope and existing response keys while adding optional `circular_linking` output:
  - `related_circulars`
  - `related_clauses`
  - each relation includes `confidence` and `rationale`.
- Added tests covering resolver structure, confidence/rationale fields, and amendment + parent-child scenarios.
