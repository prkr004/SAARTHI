import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { AuthCard } from "../components/auth/AuthCard";
import { useAuth } from "../hooks/useAuth";
import { toUserErrorMessage } from "../lib/errors";

const EMPLOYEE_ID_PATTERN = /^[A-Za-z0-9_-]{4,24}$/;
const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

function validateEmployeeId(value: string): string | null {
  if (!value) {
    return "Employee ID is required.";
  }
  if (!EMPLOYEE_ID_PATTERN.test(value)) {
    return "Employee ID must be 4-24 characters and can only contain letters, numbers, underscores, or hyphens.";
  }
  return null;
}

function validateEmail(value: string): string | null {
  if (!value) {
    return "Email address is required.";
  }
  if (!EMAIL_PATTERN.test(value)) {
    return "Please enter a valid email address.";
  }
  return null;
}

function validatePassword(value: string): string | null {
  if (value.length < 12) {
    return "Password must be at least 12 characters.";
  }

  const checks = [
    /[A-Z]/.test(value),
    /[a-z]/.test(value),
    /[0-9]/.test(value),
    /[^A-Za-z0-9]/.test(value),
  ];

  if (!checks.every(Boolean)) {
    return "Password must include uppercase, lowercase, number, and special character.";
  }

  return null;
}

export function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();

  const [fullName, setFullName] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const normalizedFullName = fullName.trim();
    const normalizedEmployeeId = employeeId.trim();
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedFullName) {
      setError("Full name is required.");
      return;
    }

    if (normalizedFullName.length < 3) {
      setError("Please enter your full name.");
      return;
    }

    const employeeIdError = validateEmployeeId(normalizedEmployeeId);
    if (employeeIdError) {
      setError(employeeIdError);
      return;
    }

    const emailError = validateEmail(normalizedEmail);
    if (emailError) {
      setError(emailError);
      return;
    }

    const passwordError = validatePassword(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const message = await register(normalizedEmployeeId, normalizedFullName, password, normalizedEmail);
      setSuccess(message);
      window.setTimeout(() => navigate("/login", { replace: true }), 1400);
    } catch (submitError) {
      setError(toUserErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Create Employee Account"
      subtitle="Register once to access persistent chat history and secure workspace controls."
      footerText="Already registered?"
      footerLinkLabel="Sign in"
      footerLinkTo="/login"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Full Name</span>
          <input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Aman Sharma" />
        </label>

        <label className="field">
          <span>Employee ID</span>
          <input
            value={employeeId}
            onChange={(event) => setEmployeeId(event.target.value)}
            placeholder="EMP1234"
            maxLength={24}
          />
        </label>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@example.com"
            autoComplete="email"
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>

        <label className="field">
          <span>Confirm Password</span>
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </label>

        <p className="form-subnote">
          Password policy: minimum 12 chars with upper, lower, number, and special character.
        </p>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {success ? (
          <p className="form-success" role="status">
            {success}
          </p>
        ) : null}

        <button type="submit" className="button button--primary" disabled={submitting}>
          {submitting ? "Creating account..." : "Create Account"}
        </button>
      </form>
    </AuthCard>
  );
}
