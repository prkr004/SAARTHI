import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "../pages/LoginPage";
import { RegisterPage } from "../pages/RegisterPage";

const loginMock = vi.fn();
const registerMock = vi.fn();

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    login: loginMock,
    register: registerMock,
    logout: vi.fn(),
    loading: false,
    isAuthenticated: false,
    user: null,
    token: null,
  }),
}));

describe("auth flow", () => {
  beforeEach(() => {
    loginMock.mockReset();
    registerMock.mockReset();
    loginMock.mockResolvedValue({
      user_id: 1,
      employee_id: "EMP7001",
      full_name: "Demo User",
      role: "user",
      approval_status: "approved",
    });
    registerMock.mockResolvedValue(
      "Your request has been sent to the admin. Once approved, you will have access to SAARTHI!",
    );
  });

  it("submits login form", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByPlaceholderText("EMP1234"), "EMP7001");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Login" }));

    expect(loginMock).toHaveBeenCalledWith("EMP7001", "SecurePass#123");
  });

  it("shows employee ID validation on login", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByPlaceholderText("EMP1234"), "bad id");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Login" }));

    expect(
      await screen.findByText(
        "Employee ID must be 4-24 characters and can only contain letters, numbers, underscores, or hyphens.",
      ),
    ).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("shows mismatch validation on register", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Full Name"), "Aman Sharma");
    await user.type(screen.getByPlaceholderText("EMP1234"), "EMP8001");
    await user.type(screen.getByLabelText("Email"), "aman.sharma@example.com");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.type(screen.getByLabelText("Confirm Password"), "SecurePass#321");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("displays pending approval registration success message", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Full Name"), "Aman Sharma");
    await user.type(screen.getByPlaceholderText("EMP1234"), "EMP8010");
    await user.type(screen.getByLabelText("Email"), "aman.sharma@example.com");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.type(screen.getByLabelText("Confirm Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(
      await screen.findByText(
        "Your request has been sent to the admin. Once approved, you will have access to SAARTHI!",
      ),
    ).toBeInTheDocument();
  });

  it("requires email on register", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Full Name"), "Aman Sharma");
    await user.type(screen.getByPlaceholderText("EMP1234"), "EMP8011");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.type(screen.getByLabelText("Confirm Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByText("Email address is required.")).toBeInTheDocument();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("renders duplicate employee id error professionally", async () => {
    const user = userEvent.setup();
    registerMock.mockRejectedValueOnce(new Error("An account with this Employee ID already exists."));

    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Full Name"), "Aman Sharma");
    await user.type(screen.getByPlaceholderText("EMP1234"), "EMP8012");
    await user.type(screen.getByLabelText("Email"), "duplicate@example.com");
    await user.type(screen.getByLabelText("Password"), "SecurePass#123");
    await user.type(screen.getByLabelText("Confirm Password"), "SecurePass#123");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByText("An account with this Employee ID already exists.")).toBeInTheDocument();
  });
});
