import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminUploadDocumentsPage } from "../pages/AdminUploadDocumentsPage";

const apiMock = vi.hoisted(() => ({
  listIngestionJobs: vi.fn(),
  createIngestionJob: vi.fn(),
  getIngestionJob: vi.fn(),
  listDocuments: vi.fn(),
  softDeleteDocument: vi.fn(),
  createBackfillJob: vi.fn(),
  getBackfillJob: vi.fn(),
}));

vi.mock("../lib/api/endpoints", () => ({
  api: apiMock,
}));

describe("admin upload progress", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    apiMock.listIngestionJobs.mockResolvedValue({ jobs: [] });

    apiMock.listDocuments.mockResolvedValue({
      documents: [
        {
          id: 901,
          document_key: "rbi|doc_registry_happy|2026-04-20",
          source: "doc_registry_happy.pdf",
          document_title: "Registry Happy Document",
          version_date: "2026-04-20",
          effective_date: "2026-04-20",
          regulator: "Reserve Bank of India",
          document_status: "Active",
          chunk_count: 4,
          metadata: { source_type: "pdf" },
          summary_status: "pending",
          summary_one_liner: null,
          summary_short: "This is a short summary for non technical users.",
          summary_error: null,
          summary_updated_at: null,
          first_seen_at: "2026-04-20T00:00:00+00:00",
          last_seen_at: "2026-04-20T00:00:00+00:00",
          created_at: "2026-04-20T00:00:00+00:00",
          updated_at: "2026-04-20T00:00:00+00:00",
          last_ingestion_job_id: null,
          is_deleted: 0,
          deleted_at: null,
          deleted_by: null,
          deleted_reason: null,
          deleted_by_employee_id: null,
          deleted_by_name: null,
        },
      ],
      total: 1,
      limit: 80,
      offset: 0,
    });

    apiMock.softDeleteDocument.mockResolvedValue({
      message: "Document soft-deleted.",
      document: {
        id: 901,
      },
    });

    apiMock.createBackfillJob.mockResolvedValue({
      message: "Backfill job created.",
      job: {
        job_id: "backfill_1",
        created_by: 1,
        created_by_employee_id: "ADMIN001",
        created_by_name: "Admin",
        created_at: "2026-04-20T00:00:00+00:00",
        updated_at: "2026-04-20T00:00:00+00:00",
        status: "completed",
        total_documents: 1,
        processed_documents: 1,
        discovered_chunks: 12,
        progress_percent: 100,
        current_document_key: null,
        error_message: null,
      },
    });

    apiMock.getBackfillJob.mockResolvedValue({
      job_id: "backfill_1",
      created_by: 1,
      created_by_employee_id: "ADMIN001",
      created_by_name: "Admin",
      created_at: "2026-04-20T00:00:00+00:00",
      updated_at: "2026-04-20T00:00:00+00:00",
      status: "completed",
      total_documents: 1,
      processed_documents: 1,
      discovered_chunks: 12,
      progress_percent: 100,
      current_document_key: null,
      error_message: null,
    });

    apiMock.createIngestionJob.mockResolvedValue({
      message: "Ingestion job created.",
      job: {
        job_id: "job_1",
        created_by: 1,
        created_by_employee_id: "ADMIN001",
        created_by_name: "Admin",
        created_at: "2026-04-19T00:00:00+00:00",
        updated_at: "2026-04-19T00:00:00+00:00",
        status: "queued",
        total_files: 1,
        processed_files: 0,
        total_chunks: 0,
        progress_percent: 0,
        current_file: null,
      },
    });

    apiMock.getIngestionJob
      .mockResolvedValueOnce({
        job_id: "job_1",
        created_by: 1,
        created_by_employee_id: "ADMIN001",
        created_by_name: "Admin",
        created_at: "2026-04-19T00:00:00+00:00",
        updated_at: "2026-04-19T00:00:01+00:00",
        status: "running",
        total_files: 1,
        processed_files: 0,
        total_chunks: 3,
        progress_percent: 40,
        current_file: "doc1.pdf",
      })
      .mockResolvedValueOnce({
        job_id: "job_1",
        created_by: 1,
        created_by_employee_id: "ADMIN001",
        created_by_name: "Admin",
        created_at: "2026-04-19T00:00:00+00:00",
        updated_at: "2026-04-19T00:00:02+00:00",
        status: "completed",
        total_files: 1,
        processed_files: 1,
        total_chunks: 7,
        progress_percent: 100,
        current_file: null,
      });
  });

  it("shows document cards with publisher, dates, and short summary", async () => {
    render(
      <MemoryRouter>
        <AdminUploadDocumentsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Registry Happy Document")).toBeInTheDocument();
    expect(screen.getByText("Publisher: RBI")).toBeInTheDocument();
    expect(screen.getByText(/Version date:/)).toBeInTheDocument();
    expect(screen.getByText("This is a short summary for non technical users.")).toBeInTheDocument();
  });

  it("supports simple delete from admin dashboard", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AdminUploadDocumentsPage />
      </MemoryRouter>,
    );

    await screen.findByText("Registry Happy Document");

    await user.click(screen.getByRole("button", { name: "Delete document" }));

    await waitFor(() => {
      expect(apiMock.softDeleteDocument).toHaveBeenCalledWith(901, "Deleted from admin dashboard.");
    });

    expect(screen.queryByText("Registry Happy Document")).not.toBeInTheDocument();
  });

  it("syncs documents with backfill and refreshes the library", async () => {
    const user = userEvent.setup();

    apiMock.listDocuments
      .mockResolvedValueOnce({
        documents: [
          {
            id: 901,
            document_key: "rbi|doc_registry_happy|2026-04-20",
            source: "doc_registry_happy.pdf",
            document_title: "Registry Happy Document",
            version_date: "2026-04-20",
            effective_date: "2026-04-20",
            regulator: "Reserve Bank of India",
            document_status: "Active",
            chunk_count: 4,
            metadata: { source_type: "pdf" },
            summary_status: "pending",
            summary_one_liner: null,
            summary_short: "This is a short summary for non technical users.",
            summary_error: null,
            summary_updated_at: null,
            first_seen_at: "2026-04-20T00:00:00+00:00",
            last_seen_at: "2026-04-20T00:00:00+00:00",
            created_at: "2026-04-20T00:00:00+00:00",
            updated_at: "2026-04-20T00:00:00+00:00",
            last_ingestion_job_id: null,
            is_deleted: 0,
            deleted_at: null,
            deleted_by: null,
            deleted_reason: null,
            deleted_by_employee_id: null,
            deleted_by_name: null,
          },
        ],
        total: 1,
        limit: 80,
        offset: 0,
      })
      .mockResolvedValueOnce({
        documents: [
          {
            id: 901,
            document_key: "rbi|doc_registry_happy|2026-04-20",
            source: "doc_registry_happy.pdf",
            document_title: "Registry Happy Document",
            version_date: "2026-04-20",
            effective_date: "2026-04-20",
            regulator: "Reserve Bank of India",
            document_status: "Active",
            chunk_count: 4,
            metadata: { source_type: "pdf" },
            summary_status: "pending",
            summary_one_liner: null,
            summary_short: "This is a short summary for non technical users.",
            summary_error: null,
            summary_updated_at: null,
            first_seen_at: "2026-04-20T00:00:00+00:00",
            last_seen_at: "2026-04-20T00:00:00+00:00",
            created_at: "2026-04-20T00:00:00+00:00",
            updated_at: "2026-04-20T00:00:00+00:00",
            last_ingestion_job_id: null,
            is_deleted: 0,
            deleted_at: null,
            deleted_by: null,
            deleted_reason: null,
            deleted_by_employee_id: null,
            deleted_by_name: null,
          },
          {
            id: 902,
            document_key: "sebi|new_doc|2026-04-20",
            source: "new_doc.pdf",
            document_title: "New Synced Document",
            version_date: "2026-04-20",
            effective_date: "2026-04-20",
            regulator: "SEBI",
            document_status: "Active",
            chunk_count: 0,
            metadata: { source_type: "manifest" },
            summary_status: "pending",
            summary_one_liner: null,
            summary_short: "Newly synchronized from corpus.",
            summary_error: null,
            summary_updated_at: null,
            first_seen_at: "2026-04-20T00:00:00+00:00",
            last_seen_at: "2026-04-20T00:00:00+00:00",
            created_at: "2026-04-20T00:00:00+00:00",
            updated_at: "2026-04-20T00:00:00+00:00",
            last_ingestion_job_id: null,
            is_deleted: 0,
            deleted_at: null,
            deleted_by: null,
            deleted_reason: null,
            deleted_by_employee_id: null,
            deleted_by_name: null,
          },
        ],
        total: 2,
        limit: 80,
        offset: 0,
      });

    render(
      <MemoryRouter>
        <AdminUploadDocumentsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Registry Happy Document")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sync documents" }));

    await waitFor(() => {
      expect(apiMock.createBackfillJob).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText("New Synced Document")).toBeInTheDocument();
    expect(await screen.findByText("Sync completed. The document list now reflects corpus data.")).toBeInTheDocument();
  });

  it("renders ingestion progress updates while polling", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AdminUploadDocumentsPage />
      </MemoryRouter>,
    );

    const fileInput = document.getElementById("admin-upload-input") as HTMLInputElement;
    const file = new File(["%PDF-1.4"], "doc1.pdf", { type: "application/pdf" });

    await user.upload(fileInput, file);
    await user.click(screen.getByRole("button", { name: "Upload and ingest" }));

    expect(await screen.findByText("Upload accepted. Ingestion has started.")).toBeInTheDocument();

    expect(await screen.findByText("Running (40%)", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(await screen.findByText("Completed (100%)", undefined, { timeout: 8000 })).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMock.getIngestionJob).toHaveBeenCalledTimes(2);
    });

    expect(await screen.findByText("Ingestion completed. Your uploaded documents are now in the RAG pipeline.")).toBeInTheDocument();
  }, 12000);

  it("renders error states for document list and ingestion status", async () => {
    apiMock.listDocuments.mockRejectedValueOnce(new Error("Document registry unavailable"));
    apiMock.listIngestionJobs.mockRejectedValueOnce(new Error("Ingestion status unavailable"));

    render(
      <MemoryRouter>
        <AdminUploadDocumentsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Document registry unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Ingestion status unavailable")).toBeInTheDocument();
  });
});
