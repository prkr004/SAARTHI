# SAARTHI - FastAPI + React Regulatory Assistant

SAARTHI is a FastAPI backend plus React frontend application for regulatory Q&A and temporal comparison over indexed documents.

## Stack

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- Retrieval: FAISS + LangChain + Ollama
- Persistence: SQLite split stores
	- Employee DB: `data/shared/saarthi_employee.db`
	- Admin DB: `data/shared/saarthi_admin.db`
	- Session DB: `data/shared/saarthi_sessions.db`

## Prerequisites

1. Python 3.12 recommended
2. Node.js 20+ and npm 10+
3. Ollama installed

## First-Time Setup

From repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env

cd frontend
npm install
Copy-Item .env.example .env
cd ..
```

Pull at least one Ollama model (example):

```powershell
ollama pull phi:2.7b
```

## Build Vector Store (required before asking RAG questions)

The build now reads a corpus manifest at `data/corpus_manifest.json`.

Every manifest entry must include these keys:

- `pdf_path`
- `regulator`
- `document_title`
- `version_date` (YYYY-MM-DD)
- `effective_date` (YYYY-MM-DD)
- `amends` (can be `null`, but key is required)

The default manifest already includes RBI + SEBI + DPDP sources from `data/`.

Run after setup, and run again whenever source PDFs or manifest entries are changed:

```powershell
.\.venv\Scripts\python.exe build_vectorstore.py
```

Optional: provide a custom manifest path.

```powershell
.\.venv\Scripts\python.exe build_vectorstore.py --manifest data/corpus_manifest.json
```

## Run The Project (3 terminals)

After dependencies are installed, run exactly as below.

Terminal 1 (root directory):

```powershell
ollama serve
```

Terminal 2 (root directory):

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000
```

Terminal 3 (inside `frontend` folder):

```powershell
cd frontend
npm run dev
```

## URLs

- Frontend: http://localhost:5173
- Admin Login: http://localhost:5173/admin/login
- Admin Dashboard: http://localhost:5173/admin/dashboard
- API docs: http://localhost:8000/docs
- Health (live): http://localhost:8000/api/v1/health/live
- Health (ready): http://localhost:8000/api/v1/health/ready

## Default Local Admin

- Employee ID: `ADMIN001`
- Password: `AdminPass#2026`

You can override these with environment variables in `.env`.

Additional admin bootstrap variables:

- `SAARTHI_ADMIN_EMPLOYEE_ID`
- `SAARTHI_ADMIN_NAME`
- `SAARTHI_ADMIN_PASSWORD`
- `SAARTHI_ADMIN_EMAIL`

Database path controls:

- `SAARTHI_EMPLOYEE_DB_PATH`
- `SAARTHI_ADMIN_DB_PATH`
- `SAARTHI_SESSION_DB_PATH`

At backend startup, the bootstrap admin is enforced to role `admin` and approval status `approved`.

## Shared Data Consistency

- Employee profiles, approvals, and chat history are persisted in the Employee DB.
- Admin credentials and admin operational records (ingestion/backfill/summary/document registry) are persisted in the Admin DB.
- API login sessions are persisted in the Session DB.
- Legacy combined database (`data/saarthi_secure.db`) is migrated automatically on startup.

## User Approval Workflow

- New user registrations are created in `pending` status by default.
- Registration success message:
	- `Your request has been sent to the admin. Once approved, you will have access to SAARTHI!`
- Pending/rejected users cannot log in.
- Admin can approve/reject requests from the admin portal.

## Email Notification Setup

Approval/rejection notifications are configurable through:

- `SAARTHI_NOTIFICATION_PROVIDER` = `noop` | `console` | `smtp`
- `SAARTHI_NOTIFICATION_FROM_EMAIL`
- `SAARTHI_NOTIFICATION_SMTP_HOST`
- `SAARTHI_NOTIFICATION_SMTP_PORT`
- `SAARTHI_NOTIFICATION_SMTP_USERNAME`
- `SAARTHI_NOTIFICATION_SMTP_PASSWORD`
- `SAARTHI_NOTIFICATION_SMTP_USE_SSL`
- `SAARTHI_NOTIFICATION_SMTP_USE_STARTTLS`

If notification delivery fails, the admin approval/rejection action still completes and returns a warning.

## Upload Limits and Ingestion

Admin ingestion settings:

- `SAARTHI_ADMIN_UPLOAD_DIRECTORY` (default `data/admin_uploads`)
- `SAARTHI_ADMIN_UPLOAD_MAX_FILES_PER_JOB` (default `12`)
- `SAARTHI_ADMIN_UPLOAD_MAX_FILE_SIZE_MB` (default `20`)

Uploaded PDFs are ingested incrementally with persistent job progress, and RAG cache refresh is triggered automatically on completion.

## Optional one-command dev start

You can also use helper scripts:

```powershell
.\scripts\dev-up.ps1
.\scripts\dev-down.ps1
```

## Validation Commands

Backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Frontend tests and build:

```powershell
cd frontend
npm run test
npm run build
```

## Troubleshooting

- If `npm run dev` says `ENOENT package.json`, run it inside `frontend`.
- If backend cannot find dependencies, activate `.venv` in that terminal.
- If model errors appear, verify `ollama serve` is running and model is pulled.
- If readiness fails on vector index, rebuild with `build_vectorstore.py`.
- If vector build fails with manifest validation errors, fix required fields in `data/corpus_manifest.json`.

## Project docs

- `docs/README.md`
- `docs/phase/`
- `docs/migration/`
- `docs/archive/`
