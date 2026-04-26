# SAARTHI

SAARTHI is a full-stack regulatory intelligence platform built to help teams search, understand, and operationalize compliance knowledge across evolving regulatory documents.

It combines semantic retrieval, temporal comparison, and workflow tooling so users can move from raw circulars and policy PDFs to actionable answers.

## What SAARTHI Solves

Regulatory and compliance teams often struggle with:

- fragmented source documents spread across versions and issuers
- slow manual lookup during audits, reviews, and implementation work
- uncertainty about how obligations changed over time
- limited traceability between answers and source text

SAARTHI addresses this by providing a single platform for ingestion, indexing, retrieval, comparison, and governed access.

## Key Features

- FastAPI backend with modular service layers
- React + TypeScript frontend for user and admin workflows
- Retrieval-Augmented Generation (RAG) over indexed documents
- Temporal comparison support for version-aware analysis
- Role-aware authentication and access control
- Password hashing and secure session-token handling
- User onboarding with approval workflow
- Admin upload pipeline for document ingestion
- Background job tracking for ingestion, backfill, and summaries
- Health and readiness endpoints for operational monitoring
- Automated backend and frontend test support

## Functional Areas

### 1) Authentication and Access

- employee and admin login flows
- approval-gated user onboarding
- session persistence in a dedicated store
- secure handling of credentials and tokens

### 2) Document Lifecycle

- manifest-driven corpus definition
- ingestion of supported regulatory PDFs
- metadata-aware indexing and storage
- document tracking for updates and governance

### 3) Retrieval and Intelligence

- semantic search over vectorized document chunks
- context-aware answer generation
- temporal intent/comparison helpers
- answer grounding using indexed source data

### 4) Admin Operations

- upload management and ingestion controls
- job state visibility (queued/running/completed/failed)
- operational workflows for reindexing and backfills
- document registry and audit-aligned process support

## How It Works

1. Configure the environment and dependencies.
2. Define source documents in the corpus manifest.
3. Build or refresh the vector index.
4. Start model serving, backend, and frontend services.
5. Users ask questions from the UI; backend retrieves context and generates responses.
6. Admins manage onboarding, ingestion jobs, and operational data quality flows.

## Tech Stack

- Backend: FastAPI
- Frontend: React, TypeScript, Vite
- Retrieval: FAISS, LangChain, Ollama-compatible local models
- Persistence: SQLite split stores (employee/admin/session)

## Repository Structure

- `backend/` API, services, schemas, tests, and operational scripts
- `frontend/` React application and frontend test/build setup
- `data/` corpus manifest, shared data stores, upload artifacts
- `docs/` migration notes, phase reports, and archived references
- `ingestion/` document loading and vectorstore build helpers
- `scripts/` development convenience scripts
- `chat_store.py` core local persistence/auth/conversation routines
- `build_vectorstore.py` index build entrypoint

## Prerequisites

- Python 3.12+ recommended
- Node.js 20+ and npm 10+
- Ollama installed and available in PATH

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

Pull at least one compatible model:

```powershell
ollama pull phi:2.7b
```

## Build Vector Store

The build process reads `data/corpus_manifest.json`.

Each manifest item must provide:

- `pdf_path`
- `regulator`
- `document_title`
- `version_date` (YYYY-MM-DD)
- `effective_date` (YYYY-MM-DD)
- `amends` (nullable, but required key)

Build commands:

```powershell
.\.venv\Scripts\python.exe build_vectorstore.py
.\.venv\Scripts\python.exe build_vectorstore.py --manifest data/corpus_manifest.json
```

## Run SAARTHI (3 Terminals)

Terminal 1 (model server):

```powershell
ollama serve
```

Terminal 2 (backend):

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000
```

Terminal 3 (frontend):

```powershell
cd frontend
npm run dev
```

## Local URLs

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/api/v1/health/live
- Readiness: http://localhost:8000/api/v1/health/ready

## Configuration and Security

SAARTHI is environment-variable driven. Keep secrets out of source control.

Recommended configuration groups:

- app/runtime settings
- database path settings
- authentication/session settings
- admin upload and ingestion limits
- notification provider settings
- model/retrieval settings

Security best practices:

- never commit credentials, secrets, or real tokens
- use local `.env` files or a secret manager per environment
- rotate credentials and review access regularly
- keep production values separate from development defaults

## Data Stores

SAARTHI uses split SQLite stores for clearer operational boundaries:

- employee store for user profiles and chat history
- admin store for operational/admin workflows
- session store for API session state

A legacy combined store can be migrated on startup where applicable.

## Validation and Testing

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

- If `npm run dev` reports missing `package.json`, run it inside `frontend/`.
- If backend imports fail, verify virtual environment activation in that terminal.
- If model-related requests fail, check that model serving is running and the model is pulled.
- If readiness fails due to vector index, rebuild using `build_vectorstore.py`.
- If manifest validation fails, fix required fields in `data/corpus_manifest.json`.

## Documentation

- `docs/README.md`
- `docs/phase/`
- `docs/migration/`
- `docs/archive/`

