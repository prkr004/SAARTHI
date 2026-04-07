# SAARTHI - Regulatory Q&A Assistant

SAARTHI is a Streamlit-based RAG assistant for RBI regulatory documents.
It supports:
- grounded Q&A over indexed circulars and guidelines
- temporal/version-aware comparisons between document editions
- source citation display with official links where available
- secure employee login/register with Employee ID
- persistent multi-chat history (ChatGPT-style) with resume support

## Project Structure

- `app.py`: Streamlit UI entry point
- `build_vectorstore.py`: builds or rebuilds FAISS index from PDFs in `data/`
- `query.py`: core retrieval + generation pipeline
- `chat_store.py`: secure local auth, conversation history, and message persistence
- `ingestion/`: PDF loading, chunking, metadata schema, vectorstore builder
- `temporal/`: intent detection, version retrieval, and clause comparison
- `ui/`: helper UI components for temporal result rendering
- `data/`: source PDFs used for ingestion
- `faiss_index/`: generated vector index (created after ingestion)

## Prerequisites

1. Python 3.11–3.12 (recommended: 3.12).
2. Ollama >= 0.50.0 installed and running locally ([ollama.ai](https://ollama.ai)).
3. Ollama model pulled locally (default in code: `llama3.1:8b`).

Example Ollama setup:

```powershell
ollama pull llama3.1:8b
ollama serve
```

If you are using the app for employee access, a universal default admin is auto-created at startup:

```text
Employee ID: ADMIN001
Password: AdminPass#2026
```

Optionally, you can override admin bootstrap credentials before launch:

```powershell
$env:SAARTHI_ADMIN_EMPLOYEE_ID = "ADMIN001"
$env:SAARTHI_ADMIN_NAME = "Bank Admin"
$env:SAARTHI_ADMIN_PASSWORD = "AdminPass#2026"
```

## Quick Start (Windows PowerShell)

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Make sure required PDFs exist in `data/`.

4. Build the FAISS index:

```powershell
python build_vectorstore.py
```

5. Run the Streamlit app:

```powershell
streamlit run app.py
```

The app will open in your browser (usually `http://localhost:8501`).

If you set the admin environment variables above, keep them in the same terminal session before launching Streamlit so the admin account is created or synced at startup.

## Secure Access And Saved Chats

- On first use, employees should register with `Full Name`, `Employee ID`, and a strong password.
- Password policy requires at least 12 characters and a mix of upper/lower/number/special characters.
- Login protection includes temporary lockout after repeated failed attempts.
- Each employee has isolated conversation storage in `data/saarthi_secure.db`.
- Chats persist across refreshes and browser restarts for the same employee.
- Sidebar includes:
  - `+ New Chat` to start a fresh conversation
  - previous chat list to reopen and continue where you left off
  - `✎` rename action and `🗑` delete action for each chat

## Admin Credentials (Bootstrap)

By default, the app auto-creates/syncs this universal admin on startup:

- Employee ID: `ADMIN001`
- Password: `AdminPass#2026`

You can override these credentials using environment variables before starting Streamlit.

Windows PowerShell:

```powershell
$env:SAARTHI_ADMIN_EMPLOYEE_ID = "ADMIN001"
$env:SAARTHI_ADMIN_NAME = "Bank Admin"
$env:SAARTHI_ADMIN_PASSWORD = "AdminPass#2026"
streamlit run app.py
```

Then login with:

- Employee ID: `ADMIN001`
- Password: `AdminPass#2026`

If the employee already exists, startup will sync the admin name/password from these environment values.

Note: Admin login is independent of Streamlit port. Whether the app opens on `localhost:8501`, `localhost:8502`, or another available port, the same admin credentials work.

## Quick Start (macOS/Linux)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build_vectorstore.py
streamlit run app.py
```

## How Teammates Should Work

1. Pull latest code (skip `.venv/`, `__pycache__/`, `faiss_index/` — they're in `.gitignore`).
2. Create fresh virtual environment: `python -m venv .venv`.
3. Activate it and install: `pip install -r requirements.txt`.
4. Ensure Ollama is running: `ollama serve` (in separate terminal).
5. Rebuild index after any PDF changes: `python build_vectorstore.py`.
6. Start app: `streamlit run app.py`.

## Common Issues

- Error: FAISS index not found
  - Cause: index not built yet.
  - Fix: run `python build_vectorstore.py`.

- Empty or weak answers
  - Cause: relevant document not ingested.
  - Fix: add/update PDFs in `data/` and rebuild index.

- LLM call errors during temporal comparison
  - Cause: Ollama not running or model not present.
  - Fix: ensure `ollama serve` is active and `ollama pull llama3` is completed.

## Rebuilding vs Incremental Ingestion

- Full rebuild: `python build_vectorstore.py`
- Incremental add: use `ingestion.vectorstore_builder.add_to_vectorstore(...)` from Python code.

## Notes

- `faiss_index/` and local virtual environments are ignored by git.
- Do not commit `.env` or local secret files.
