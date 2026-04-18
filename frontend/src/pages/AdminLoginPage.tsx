import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthCard } from "../components/auth/AuthCard";
import { useAuth } from "../hooks/useAuth";
import { toUserErrorMessage } from "../lib/errors";

const EMPLOYEE_ID_PATTERN = /^[A-Za-z0-9_-]{4,24}$/;

function validateEmployeeId(value: string): string | null {
  if (!value) {
    return "Admin Employee ID is required.";
  }
  if (!EMPLOYEE_ID_PATTERN.test(value)) {
    return "Admin Employee ID must be 4-24 characters and can only contain letters, numbers, underscores, or hyphens.";
  }
  return null;
}

export function AdminLoginPage() {
  const navigate = useNavigate();
  const { login, logout } = useAuth();

  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const normalizedEmployeeId = employeeId.trim();

    const employeeIdError = validateEmployeeId(normalizedEmployeeId);
    if (employeeIdError) {
      setError(employeeIdError);
      return;
    }

    if (!password.trim()) {
      setError("Password is required.");
      return;
    }

    setSubmitting(true);
    try {
      const profile = await login(normalizedEmployeeId, password);
      if (profile.role !== "admin") {
        await logout();
        setError("This portal is restricted to admin users.");
        return;
      }
      navigate("/admin/dashboard", { replace: true });
    } catch (submitError) {
      setError(toUserErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Admin Portal Sign-In"
      subtitle="Manage user approvals and ingestion jobs for SAARTHI operations."
      footerText="Are you an employee user?"
      footerLinkLabel="Open employee login"
      footerLinkTo="/login"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Admin Employee ID</span>
          <input
            value={employeeId}
            onChange={(event) => setEmployeeId(event.target.value)}
            placeholder="ADMIN001"
            maxLength={24}
            autoComplete="username"
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button--primary" disabled={submitting}>
          {submitting ? "Signing in..." : "Login as Admin"}
        </button>
      </form>

      <p className="small-link">
        <Link to="/">Return to workspace home</Link>
      </p>
    </AuthCard>
  );
}
