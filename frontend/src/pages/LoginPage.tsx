import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthCard } from "../components/auth/AuthCard";
import { useAuth } from "../hooks/useAuth";
import { toUserErrorMessage } from "../lib/errors";

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!employeeId.trim() || !password.trim()) {
      setError("Please enter Employee ID and password.");
      return;
    }

    setSubmitting(true);
    try {
      await login(employeeId.trim(), password);
      navigate("/", { replace: true });
    } catch (submitError) {
      setError(toUserErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Secure Employee Login"
      subtitle="Access SAARTHI to query regulatory guidance with auditable sources."
      footerText="New employee?"
      footerLinkLabel="Create an account"
      footerLinkTo="/register"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Employee ID</span>
          <input
            value={employeeId}
            onChange={(event) => setEmployeeId(event.target.value)}
            placeholder="EMP1234"
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
          {submitting ? "Signing in..." : "Login"}
        </button>

        <p className="form-subnote">
          By continuing, you agree to use this assistant for regulatory research support and verify with official RBI circulars.
        </p>
      </form>

      <p className="small-link">
        <Link to="/">Return to workspace home</Link>
      </p>
    </AuthCard>
  );
}
