# SAARTHI Frontend

React + TypeScript frontend for SAARTHI (Phase 4 and Phase 5 hardening).

## Local Run

1. Install dependencies:

```powershell
npm install
```

2. Configure env:

```powershell
Copy-Item .env.example .env
```

3. Start dev server:

```powershell
npm run dev
```

Default URL: http://localhost:5173

Admin URLs:

- http://localhost:5173/admin/login
- http://localhost:5173/admin/dashboard

## Environment Variables

- VITE_API_BASE_URL
  - Default: http://localhost:8000/api/v1

## Admin UX Notes

- Admin routes are guarded client-side and require authenticated `role=admin`.
- Admin dashboard includes feature cards for:
  - RAG Chatbot (routes to existing chat module)
  - Document Generator (routes to existing drafting module)
  - Authenticate Users
  - Upload Documents
- Upload Documents panel performs live progress polling for ingestion jobs.

## Scripts

- npm run dev
- npm run build
- npm run test
- npm run test:watch

## QA Commands

```powershell
npm run test
npm run build
```

## Troubleshooting

- API request failures:
  - Verify backend is running on configured VITE_API_BASE_URL.
- 401/session errors:
  - Re-login and verify backend auth endpoints are healthy.
- Source links missing:
  - Check backend response formatted_sources payload.

## Related Documents

- ../docs/migration/PHASE4_FRONTEND_DELIVERABLES.md
- ../docs/phase/PHASE5_PRODUCTION_READINESS_REPORT.md
- ../docs/phase/PHASE5_POST_LAUNCH_MONITORING_CHECKLIST.md
