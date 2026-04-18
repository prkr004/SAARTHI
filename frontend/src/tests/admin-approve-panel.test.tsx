import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminUserApprovalPage } from "../pages/AdminUserApprovalPage";

const apiMock = vi.hoisted(() => ({
  listPendingUsers: vi.fn(),
  approveUser: vi.fn(),
  rejectUser: vi.fn(),
}));

vi.mock("../lib/api/endpoints", () => ({
  api: apiMock,
}));

describe("admin user approval panel", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    apiMock.listPendingUsers.mockResolvedValue([
      {
        id: 101,
        employee_id: "EMP9002",
        full_name: "Pending User",
        email: "pending@example.com",
        role: "user",
        approval_status: "pending",
        created_at: "2026-04-19T00:00:00+00:00",
      },
    ]);

    apiMock.approveUser.mockResolvedValue({
      message: "User approved successfully.",
      user: {
        id: 101,
        employee_id: "EMP9002",
        full_name: "Pending User",
        role: "user",
        approval_status: "approved",
        created_at: "2026-04-19T00:00:00+00:00",
      },
    });

    apiMock.rejectUser.mockResolvedValue({
      message: "User rejected successfully.",
      user: {
        id: 101,
        employee_id: "EMP9002",
        full_name: "Pending User",
        role: "user",
        approval_status: "rejected",
        created_at: "2026-04-19T00:00:00+00:00",
      },
    });
  });

  it("optimistically removes user and confirms approval", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AdminUserApprovalPage />
      </MemoryRouter>,
    );

    await screen.findByText("Pending User");
    await user.click(screen.getByRole("button", { name: "Approve Pending User" }));

    await waitFor(() => {
      expect(apiMock.approveUser).toHaveBeenCalledWith(101, "Approved by admin");
    });

    expect(screen.queryByText("Pending User")).not.toBeInTheDocument();
    expect(await screen.findByText("User approved successfully.")).toBeInTheDocument();
  });

  it("rolls back optimistic update when reject call fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "prompt").mockReturnValue("Not enough details");
    apiMock.rejectUser.mockRejectedValue(new Error("Reject failed"));

    render(
      <MemoryRouter>
        <AdminUserApprovalPage />
      </MemoryRouter>,
    );

    await screen.findByText("Pending User");
    await user.click(screen.getByRole("button", { name: "Reject Pending User" }));

    expect(await screen.findByText("Reject failed")).toBeInTheDocument();
    expect(await screen.findByText("Pending User")).toBeInTheDocument();
  });
});
