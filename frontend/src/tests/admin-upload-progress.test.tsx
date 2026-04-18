import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminUploadDocumentsPage } from "../pages/AdminUploadDocumentsPage";

const apiMock = vi.hoisted(() => ({
  listIngestionJobs: vi.fn(),
  createIngestionJob: vi.fn(),
  getIngestionJob: vi.fn(),
}));

vi.mock("../lib/api/endpoints", () => ({
  api: apiMock,
}));

describe("admin upload progress", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    apiMock.listIngestionJobs.mockResolvedValue({ jobs: [] });
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
    await user.click(screen.getByRole("button", { name: "Upload and Ingest" }));

    expect(
      await screen.findByText("Upload accepted. Ingestion has started and progress is now being tracked."),
    ).toBeInTheDocument();

    expect(await screen.findByText("Running (40%)", undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(await screen.findByText("Completed (100%)", undefined, { timeout: 8000 })).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMock.getIngestionJob).toHaveBeenCalledTimes(2);
    });

    expect(
      await screen.findByText("Ingestion completed. Newly uploaded documents are now available in RAG search."),
    ).toBeInTheDocument();
  }, 12000);
});
