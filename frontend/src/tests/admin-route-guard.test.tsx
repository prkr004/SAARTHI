import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminRoute } from "../routes/AdminRoute";

const authState = vi.hoisted(() => ({
  loading: false,
  isAuthenticated: false,
  user: null as null | {
    user_id: number;
    employee_id: string;
    full_name: string;
    role: "admin" | "user";
    approval_status: "approved";
  },
}));

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    ...authState,
    token: null,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

function renderGuard(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<AdminRoute />}>
          <Route path="/admin/dashboard" element={<div>Admin Dashboard</div>} />
        </Route>
        <Route path="/admin/login" element={<div>Admin Login</div>} />
        <Route path="/" element={<div>User Home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("admin route guard", () => {
  beforeEach(() => {
    authState.loading = false;
    authState.isAuthenticated = false;
    authState.user = null;
  });

  it("redirects unauthenticated users to admin login", async () => {
    renderGuard("/admin/dashboard");
    expect(await screen.findByText("Admin Login")).toBeInTheDocument();
  });

  it("redirects non-admin users to workspace home", async () => {
    authState.isAuthenticated = true;
    authState.user = {
      user_id: 12,
      employee_id: "EMP7010",
      full_name: "Regular User",
      role: "user",
      approval_status: "approved",
    };

    renderGuard("/admin/dashboard");
    expect(await screen.findByText("User Home")).toBeInTheDocument();
  });

  it("allows admin users into protected admin routes", async () => {
    authState.isAuthenticated = true;
    authState.user = {
      user_id: 1,
      employee_id: "ADMIN001",
      full_name: "Admin User",
      role: "admin",
      approval_status: "approved",
    };

    renderGuard("/admin/dashboard");
    expect(await screen.findByText("Admin Dashboard")).toBeInTheDocument();
  });
});
