import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminLoginPage } from "../pages/AdminLoginPage";

const loginMock = vi.fn();
const logoutMock = vi.fn();

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    login: loginMock,
    logout: logoutMock,
    loading: false,
    isAuthenticated: false,
    user: null,
    token: null,
    register: vi.fn(),
  }),
}));

describe("admin login validation", () => {
  beforeEach(() => {
    loginMock.mockReset();
    logoutMock.mockReset();
    loginMock.mockResolvedValue({
      user_id: 1,
      employee_id: "ADMIN001",
      full_name: "Admin",
      role: "admin",
      approval_status: "approved",
    });
  });

  it("shows employee id format validation", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AdminLoginPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByPlaceholderText("ADMIN001"), "bad id");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Login as Admin" }));

    expect(
      await screen.findByText(
        "Admin Employee ID must be 4-24 characters and can only contain letters, numbers, underscores, or hyphens.",
      ),
    ).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("logs out and blocks non-admin users", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValueOnce({
      user_id: 99,
      employee_id: "EMP9001",
      full_name: "Normal User",
      role: "user",
      approval_status: "approved",
    });

    render(
      <MemoryRouter>
        <AdminLoginPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByPlaceholderText("ADMIN001"), "EMP9001");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Login as Admin" }));

    expect(await screen.findByText("This portal is restricted to admin users.")).toBeInTheDocument();
    expect(logoutMock).toHaveBeenCalledTimes(1);
  });
});
