import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api/endpoints";
import type { DocumentRegistryRecord, IngestionJobSummary } from "../lib/api/types";
import { toUserErrorMessage } from "../lib/errors";

function isActiveJob(status: IngestionJobSummary["status"]): boolean {
  return status === "queued" || status === "running";
}

function statusLabel(status: IngestionJobSummary["status"]): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}

function formatDateLabel(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function inferPublisher(document: DocumentRegistryRecord): string {
  const regulator = (document.regulator || "").trim();
  const source = (document.source || "").toLowerCase();
  const title = (document.document_title || "").toLowerCase();
  const normalizedRegulator = regulator.toLowerCase();

  if (normalizedRegulator.includes("reserve bank of india") || normalizedRegulator === "rbi") {
    return "RBI";
  }
  if (normalizedRegulator.includes("securities and exchange board") || normalizedRegulator === "sebi") {
    return "SEBI";
  }
  if (normalizedRegulator.includes("insurance regulatory and development authority") || normalizedRegulator === "irdai") {
    return "IRDAI";
  }
  if (normalizedRegulator.includes("pension fund regulatory and development authority") || normalizedRegulator === "pfrda") {
    return "PFRDA";
  }
  if (normalizedRegulator.includes("ministry of corporate affairs") || normalizedRegulator === "mca") {
    return "MCA";
  }
  if (normalizedRegulator.includes("nabard")) {
    return "NABARD";
  }

  if (source.includes("rbi") || title.includes("rbi")) {
    return "RBI";
  }
  if (source.includes("sebi") || title.includes("sebi")) {
    return "SEBI";
  }
  if (source.includes("irdai") || title.includes("irdai")) {
    return "IRDAI";
  }
  if (source.includes("pfrda") || title.includes("pfrda")) {
    return "PFRDA";
  }
  if (source.includes("mca") || title.includes("mca")) {
    return "MCA";
  }

  if (regulator) {
    return regulator;
  }

  return "Unknown";
}

function twoLineSummary(document: DocumentRegistryRecord): string {
  const summary = (document.summary_short || document.summary_one_liner || "").trim();
  if (summary) {
    return summary;
  }

  return "Summary is being prepared. This document is already available in the RAG pipeline.";
}

export function AdminUploadDocumentsPage() {
  const SYNC_POLL_ATTEMPTS = 300;
  const SYNC_POLL_INTERVAL_MS = 1200;

  const navigate = useNavigate();

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [activeJob, setActiveJob] = useState<IngestionJobSummary | null>(null);
  const [ingestionLoading, setIngestionLoading] = useState(true);
  const [ingestionError, setIngestionError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentRegistryRecord[]>([]);
  const [documentsTotal, setDocumentsTotal] = useState(0);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [documentQuery, setDocumentQuery] = useState("");
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(null);
  const [syncingDocuments, setSyncingDocuments] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadIngestionStatus() {
    setIngestionLoading(true);
    setIngestionError(null);

    try {
      const payload = await api.listIngestionJobs(8);
      setActiveJob((current) => {
        const active = payload.jobs.find((job) => isActiveJob(job.status));
        if (active) {
          return active;
        }
        if (current) {
          return current;
        }
        return payload.jobs[0] || null;
      });
    } catch (loadError) {
      setIngestionError(toUserErrorMessage(loadError));
    } finally {
      setIngestionLoading(false);
    }
  }

  async function loadDocuments(queryOverride?: string) {
    const searchValue = (queryOverride ?? documentQuery).trim();

    setDocumentsLoading(true);
    setDocumentsError(null);

    try {
      const payload = await api.listDocuments({
        q: searchValue || undefined,
        limit: 80,
        offset: 0,
      });

      setDocuments(payload.documents);
      setDocumentsTotal(payload.total);
    } catch (loadError) {
      setDocumentsError(toUserErrorMessage(loadError));
    } finally {
      setDocumentsLoading(false);
    }
  }

  useEffect(() => {
    void loadIngestionStatus();
    void loadDocuments("");
  }, []);

  useEffect(() => {
    if (!activeJob || !isActiveJob(activeJob.status)) {
      return;
    }

    let cancelled = false;

    const timer = window.setInterval(async () => {
      try {
        const latest = await api.getIngestionJob(activeJob.job_id);
        if (cancelled) {
          return;
        }

        setActiveJob(latest);

        if (!isActiveJob(latest.status)) {
          void loadIngestionStatus();

          if (latest.status === "completed") {
            setNotice("Ingestion completed. Your uploaded documents are now in the RAG pipeline.");
            setError(null);
            void loadDocuments();
          }

          if (latest.status === "failed") {
            setError(latest.error_message || "Ingestion job failed.");
          }
        }
      } catch (pollError) {
        if (cancelled) {
          return;
        }
        setError(toUserErrorMessage(pollError));
      }
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeJob]);

  const canUpload = selectedFiles.length > 0 && !submitting;

  const activeStatusText = useMemo(() => {
    if (!activeJob) {
      return "No active ingestion job.";
    }
    return `${statusLabel(activeJob.status)} (${activeJob.progress_percent}%)`;
  }, [activeJob]);

  async function handleUpload() {
    if (!selectedFiles.length) {
      setError("Select one or more PDF files before uploading.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const response = await api.createIngestionJob(selectedFiles);
      setActiveJob(response.job);
      setNotice("Upload accepted. Ingestion has started.");
      setSelectedFiles([]);
      await loadIngestionStatus();
    } catch (uploadError) {
      setError(toUserErrorMessage(uploadError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteDocument(document: DocumentRegistryRecord) {
    const confirmed = window.confirm(`Delete \"${document.document_title}\" from the RAG pipeline?`);
    if (!confirmed) {
      return;
    }

    setDeletingDocumentId(document.id);
    setError(null);
    setNotice(null);

    try {
      await api.softDeleteDocument(document.id, "Deleted from admin dashboard.");
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setDocumentsTotal((current) => Math.max(0, current - 1));
      setNotice(`Deleted \"${document.document_title}\" from the RAG pipeline.`);
    } catch (deleteError) {
      setError(toUserErrorMessage(deleteError));
    } finally {
      setDeletingDocumentId(null);
    }
  }

  async function handleSyncDocuments() {
    setSyncingDocuments(true);
    setError(null);
    setNotice("Sync started. Pulling latest corpus documents into the registry...");

    try {
      const created = await api.createBackfillJob();
      let latest = created.job;

      for (let attempt = 0; attempt < SYNC_POLL_ATTEMPTS; attempt += 1) {
        if (latest.status === "completed" || latest.status === "failed") {
          break;
        }

        latest = await api.getBackfillJob(latest.job_id);
        if (latest.status === "completed" || latest.status === "failed") {
          break;
        }

        await new Promise<void>((resolve) => {
          window.setTimeout(() => resolve(), SYNC_POLL_INTERVAL_MS);
        });
      }

      if (latest.status === "failed") {
        setError(latest.error_message || "Document sync failed.");
        return;
      }

      setDocumentQuery("");
      await loadDocuments("");

      if (latest.status === "completed") {
        setNotice("Sync completed. The document list now reflects corpus data.");
      } else {
        setNotice("Sync is still running in background. The list was refreshed with latest available data.");
      }
    } catch (syncError) {
      setError(toUserErrorMessage(syncError));
    } finally {
      setSyncingDocuments(false);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div>
          <p className="admin-eyebrow">Upload Documents</p>
          <h1>Upload & Manage RAG Documents</h1>
          <p>Use this page to upload new PDFs and manage documents currently available to the assistant.</p>
        </div>
        <div className="admin-header__actions">
          <button type="button" className="button button--ghost" onClick={() => navigate("/admin/dashboard")}>
            Back to dashboard
          </button>
        </div>
      </header>

      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}

      {notice ? (
        <p className="notice notice--success" role="status">
          {notice}
        </p>
      ) : null}

      <section className="admin-panel" aria-label="Document upload controls">
        <div className="upload-progress-head">
          <h2>1. Upload and ingest</h2>
          <button type="button" className="button button--ghost button--compact" onClick={() => void loadIngestionStatus()}>
            Refresh status
          </button>
        </div>

        <p className="hint">Select PDF files and click upload. They will be added to the RAG pipeline.</p>

        <div className="upload-controls">
          <label className="button button--ghost upload-picker" htmlFor="admin-upload-input">
            Select documents
          </label>
          <input
            id="admin-upload-input"
            className="upload-input"
            type="file"
            multiple
            accept=".pdf,application/pdf"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              setSelectedFiles(files);
            }}
          />

          <button type="button" className="button button--primary" onClick={() => void handleUpload()} disabled={!canUpload}>
            {submitting ? "Uploading..." : "Upload and ingest"}
          </button>
        </div>

        <p className="hint">{selectedFiles.length} file(s) selected.</p>

        {selectedFiles.length > 0 ? (
          <ul className="upload-file-list" aria-label="Selected files">
            {selectedFiles.map((file) => (
              <li key={`${file.name}-${file.size}`}>{file.name}</li>
            ))}
          </ul>
        ) : null}

        {ingestionLoading ? (
          <p className="hint" role="status" aria-live="polite">
            Checking ingestion status...
          </p>
        ) : null}

        {ingestionError ? (
          <p className="notice notice--error" role="alert">
            {ingestionError}
          </p>
        ) : null}

        <div className="upload-progress-head">
          <h2>Current ingestion status</h2>
          <span className={`job-pill job-pill--${activeJob?.status || "idle"}`}>{activeStatusText}</span>
        </div>

        <div
          className="progress-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={activeJob?.progress_percent ?? 0}
        >
          <div className="progress-fill" style={{ width: `${activeJob?.progress_percent ?? 0}%` }} />
        </div>

        {activeJob ? (
          <p className="hint">
            Processed {activeJob.processed_files} / {activeJob.total_files} files. Current file: {activeJob.current_file || "-"}
          </p>
        ) : null}
      </section>

      <section className="admin-panel" aria-label="RAG document library">
        <div className="upload-progress-head">
          <h2>2. Documents currently in the RAG pipeline</h2>
          <div className="document-library-actions">
            <button
              type="button"
              className="button button--ghost button--compact"
              onClick={() => void handleSyncDocuments()}
              disabled={syncingDocuments}
            >
              {syncingDocuments ? "Syncing..." : "Sync documents"}
            </button>
            <span className="pill">{documentsTotal} total</span>
          </div>
        </div>

        <p className="hint">Each document shows publisher, dates, a short summary, and a simple delete action.</p>

        <form
          className="document-toolbar"
          onSubmit={(event) => {
            event.preventDefault();
            void loadDocuments();
          }}
        >
          <label className="field">
            <span>Search</span>
            <input
              value={documentQuery}
              onChange={(event) => setDocumentQuery(event.target.value)}
              placeholder="Search by title, source, or publisher"
            />
          </label>

          <button type="submit" className="button button--ghost">
            Search
          </button>

          <button
            type="button"
            className="button button--ghost"
            onClick={() => {
              setDocumentQuery("");
              void loadDocuments("");
            }}
          >
            Clear
          </button>
        </form>

        {documentsError ? (
          <p className="notice notice--error" role="alert">
            {documentsError}
          </p>
        ) : null}

        {documentsLoading ? (
          <p className="hint" role="status" aria-live="polite">
            Loading documents...
          </p>
        ) : null}

        {!documentsLoading && !documentsError && documents.length === 0 ? (
          <p className="hint" role="status">
            No documents found.
          </p>
        ) : null}

        <ul className="document-list" aria-label="Document registry records">
          {documents.map((document) => {
            const isDeleting = deletingDocumentId === document.id;

            return (
              <li key={document.id} className="document-card">
                <div className="document-card__top">
                  <div className="document-card__meta">
                    <h3>{document.document_title}</h3>
                    <p>Publisher: {inferPublisher(document)}</p>
                    <p>
                      Version date: {formatDateLabel(document.version_date)} | Effective date: {formatDateLabel(document.effective_date)}
                    </p>
                  </div>

                  <div className="document-card__actions">
                    <button
                      type="button"
                      className="button button--danger button--compact"
                      onClick={() => void handleDeleteDocument(document)}
                      disabled={isDeleting}
                    >
                      {isDeleting ? "Deleting..." : "Delete document"}
                    </button>
                  </div>
                </div>

                <p className="document-summary-copy document-summary-copy--two-line">{twoLineSummary(document)}</p>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
