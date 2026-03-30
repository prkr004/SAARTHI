# SAARTHI - Regulatory Q&A Assistant

SAARTHI is a Streamlit-based RAG assistant for RBI regulatory documents.
It supports:
- grounded Q&A over indexed circulars and guidelines
- temporal/version-aware comparisons between document editions
- source citation display with official links where available

## Project Structure

- `app.py`: Streamlit UI entry point
- `build_vectorstore.py`: builds or rebuilds FAISS index from PDFs in `data/`
- `query.py`: core retrieval + generation pipeline
- `ingestion/`: PDF loading, chunking, metadata schema, vectorstore builder
- `temporal/`: intent detection, version retrieval, and clause comparison
- `ui/`: helper UI components for temporal result rendering
- `data/`: source PDFs used for ingestion
- `faiss_index/`: generated vector index (created after ingestion)

## Prerequisites

1. Python 3.11+ (the project was developed with Python 3.14).
2. Ollama installed and running locally.
3. Ollama model pulled locally (default in code: `llama3`).

Example Ollama setup:

```powershell
ollama serve
ollama pull llama3
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

## Quick Start (macOS/Linux)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build_vectorstore.py
streamlit run app.py
```

## How Teammates Should Work

1. Pull latest code.
2. Create fresh virtual environment.
3. Run `pip install -r requirements.txt`.
4. Rebuild index after any PDF changes: `python build_vectorstore.py`.
5. Start app: `streamlit run app.py`.

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
