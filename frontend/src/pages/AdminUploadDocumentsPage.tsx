import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api/endpoints";
import type { IngestionJobSummary } from "../lib/api/types";
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

export function AdminUploadDocumentsPage() {
  const navigate = useNavigate();

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [activeJob, setActiveJob] = useState<IngestionJobSummary | null>(null);
  const [recentJobs, setRecentJobs] = useState<IngestionJobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadRecentJobs() {
    try {
      const payload = await api.listIngestionJobs(8);
      setRecentJobs(payload.jobs);
    } catch (loadError) {
      setError(toUserErrorMessage(loadError));
    }
  }

  useEffect(() => {
    void loadRecentJobs();
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
          void loadRecentJobs();
          if (latest.status === "completed") {
            setNotice("Ingestion completed. Newly uploaded documents are now available in RAG search.");
            setError(null);
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
      setNotice("Upload accepted. Ingestion has started and progress is now being tracked.");
      setSelectedFiles([]);
      await loadRecentJobs();
    } catch (uploadError) {
      setError(toUserErrorMessage(uploadError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div>
          <p className="admin-eyebrow">Upload Documents</p>
          <h1>Ingestion Pipeline Control</h1>
          <p>Upload multiple PDFs, monitor ingestion progress, and keep RAG retrieval aligned with latest corpus.</p>
        </div>
        <div className="admin-header__actions">
          <button type="button" className="button button--ghost" onClick={() => navigate("/admin/dashboard")}>
            Back to dashboard
          </button>
          <button type="button" className="button" onClick={() => navigate("/admin/users")}>
            Authenticate users
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
        <div className="upload-controls">
          <label className="button button--ghost upload-picker" htmlFor="admin-upload-input">
            Select Documents
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
            {submitting ? "Uploading..." : "Upload and Ingest"}
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
      </section>

      <section className="admin-panel" aria-label="Ingestion progress">
        <div className="upload-progress-head">
          <h2>Live Progress</h2>
          <span className={`job-pill job-pill--${activeJob?.status || "idle"}`}>{activeStatusText}</span>
        </div>

        <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={activeJob?.progress_percent ?? 0}>
          <div className="progress-fill" style={{ width: `${activeJob?.progress_percent ?? 0}%` }} />
        </div>

        {activeJob ? (
          <p className="hint">
            Processed {activeJob.processed_files} / {activeJob.total_files} files. Current file: {activeJob.current_file || "-"}
          </p>
        ) : null}
      </section>

      <section className="admin-panel" aria-label="Recent ingestion jobs">
        <div className="upload-progress-head">
          <h2>Recent Jobs</h2>
          <button type="button" className="button button--ghost button--compact" onClick={() => void loadRecentJobs()}>
            Refresh
          </button>
        </div>

        {recentJobs.length === 0 ? <p className="hint">No ingestion jobs yet.</p> : null}

        <ul className="job-list">
          {recentJobs.map((job) => (
            <li key={job.job_id} className="job-list-item">
              <div>
                <strong>{job.job_id}</strong>
                <p>
                  {statusLabel(job.status)} | {job.progress_percent}% | {job.processed_files}/{job.total_files} files
                </p>
              </div>
              <button
                type="button"
                className="button button--ghost button--compact"
                onClick={async () => {
                  try {
                    const latest = await api.getIngestionJob(job.job_id);
                    setActiveJob(latest);
                  } catch (refreshError) {
                    setError(toUserErrorMessage(refreshError));
                  }
                }}
              >
                View
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
