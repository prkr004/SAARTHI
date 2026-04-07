# SAARTHI Frontend

React + TypeScript frontend for SAARTHI (Phase 4 and Phase 5 hardening).

## Local Run

1. Install dependencies:

```powershell
cd "C:\4th Year\cap_trial\frontend"
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

## Environment Variables

- VITE_API_BASE_URL
  - Default: http://localhost:8000/api/v1

## Scripts

- npm run dev
- npm run build
- npm run test
- npm run test:watch

## QA Commands

```powershell
cd "C:\4th Year\cap_trial\frontend"
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
