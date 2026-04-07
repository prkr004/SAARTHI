# SAARTHI - FastAPI + React Regulatory Assistant

SAARTHI is now a FastAPI backend plus React frontend application for RBI regulatory Q&A and temporal comparison.

## Current Architecture

- Backend API: `backend/` (FastAPI)
- Frontend UI: `frontend/` (React + TypeScript + Vite)
- Retrieval + temporal logic: `query.py`, `temporal/`, `ingestion/`
- Persistence/auth store: `chat_store.py`

Legacy UI implementation has been retired from active runtime and archived under `docs/archive/legacy_ui/`.

## Prerequisites

1. Python 3.12 recommended (`.venv` local environment).
2. Node.js 20+ and npm 10+.
3. Ollama installed and running locally.
4. Required model pulled locally (example: `phi:2.7b`).

Example Ollama setup:

```powershell
ollama pull phi:2.7b
ollama serve
```

## First-Time Setup

```powershell
cd "C:\4th Year\cap_trial"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd frontend
npm install
cd ..

Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env
```

Build/rebuild vector index (when data changes):

```powershell
cd "C:\4th Year\cap_trial"
.\.venv\Scripts\python.exe build_vectorstore.py
```

## One-Command Local Run

Start backend + frontend in separate shells:

```powershell
cd "C:\4th Year\cap_trial"
./scripts/dev-up.ps1
```

Stop both:

```powershell
cd "C:\4th Year\cap_trial"
./scripts/dev-down.ps1
```

Default URLs:

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health live: http://localhost:8000/api/v1/health/live

## Manual Dev Commands

Backend:

```powershell
cd "C:\4th Year\cap_trial"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Frontend:

```powershell
cd "C:\4th Year\cap_trial\frontend"
npm run dev
```

## Test and Build Commands

Backend tests:

```powershell
cd "C:\4th Year\cap_trial"
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Frontend tests + build:

```powershell
cd "C:\4th Year\cap_trial\frontend"
npm run test
npm run build
```

## Troubleshooting

- `model_unavailable` or generation failures:
  - Ensure `ollama serve` is running and the selected model is pulled.
- Vector index/readiness failures:
  - Rebuild with `build_vectorstore.py` and verify `faiss_index/` exists.
- 401/session errors:
  - Re-login and verify backend auth endpoints are healthy.
- CORS/trusted host errors:
  - Validate `.env` values for `SAARTHI_CORS_ALLOWED_ORIGINS` and `SAARTHI_TRUSTED_HOSTS`.

## Documentation

- Documentation map: `docs/README.md`
- Phase 5 operational docs: `docs/phase/`
- Migration history docs: `docs/migration/`
- Legacy historical notes: `docs/archive/`
