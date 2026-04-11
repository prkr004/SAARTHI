# SAARTHI - FastAPI + React Regulatory Assistant

SAARTHI is a FastAPI backend plus React frontend application for regulatory Q&A and temporal comparison over indexed documents.

## Stack

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- Retrieval: FAISS + LangChain + Ollama
- Persistence: SQLite (`data/saarthi_secure.db`)

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

Run after setup, and run again whenever source PDFs are changed:

```powershell
.\.venv\Scripts\python.exe build_vectorstore.py
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
- API docs: http://localhost:8000/docs
- Health (live): http://localhost:8000/api/v1/health/live
- Health (ready): http://localhost:8000/api/v1/health/ready

## Default Local Admin

- Employee ID: `ADMIN001`
- Password: `AdminPass#2026`

You can override these with environment variables in `.env`.

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

## Project docs

- `docs/README.md`
- `docs/phase/`
- `docs/migration/`
- `docs/archive/`
