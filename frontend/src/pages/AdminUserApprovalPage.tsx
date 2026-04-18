import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api/endpoints";
import type { AdminUserSummary } from "../lib/api/types";
import { toUserErrorMessage } from "../lib/errors";

const EMPLOYEE_ID_PATTERN = /^[A-Za-z0-9_-]{4,24}$/;

function normalizeEmployeeId(value: string): string {
  return value.trim().toUpperCase();
}

export function AdminUserApprovalPage() {
  const navigate = useNavigate();

  const [pendingUsers, setPendingUsers] = useState<AdminUserSummary[]>([]);
  const [activeUsers, setActiveUsers] = useState<AdminUserSummary[]>([]);
  const [grantEmployeeId, setGrantEmployeeId] = useState("");
  const [grantReason, setGrantReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [actioningUserId, setActioningUserId] = useState<number | null>(null);
  const [granting, setGranting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refreshUsers() {
    const [pendingRows, activePayload] = await Promise.all([
      api.listPendingUsers(),
      api.listActiveUsers(),
    ]);
    setPendingUsers(pendingRows);
    setActiveUsers(activePayload.users);
  }

  useEffect(() => {
    let active = true;

    async function loadPendingUsers() {
      setLoading(true);
      setError(null);
      try {
        const [pendingRows, activePayload] = await Promise.all([
          api.listPendingUsers(),
          api.listActiveUsers(),
        ]);
        if (!active) {
          return;
        }
        setPendingUsers(pendingRows);
        setActiveUsers(activePayload.users);
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(toUserErrorMessage(loadError));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadPendingUsers();

    return () => {
      active = false;
    };
  }, []);

  async function handleDecision(user: AdminUserSummary, decision: "approve" | "reject") {
    setError(null);
    setNotice(null);

    const snapshot = pendingUsers;
    const activeSnapshot = activeUsers;
    setPendingUsers((current) => current.filter((item) => item.id !== user.id));
    if (decision === "approve") {
      setActiveUsers((current) => {
        if (current.some((item) => item.id === user.id)) {
          return current;
        }
        return [{ ...user, approval_status: "approved" }, ...current];
      });
    }
    setActioningUserId(user.id);

    const reviewReason =
      decision === "reject"
        ? window.prompt("Optional rejection reason", "")?.trim() || undefined
        : "Approved by admin";

    try {
      const result =
        decision === "approve"
          ? await api.approveUser(user.id, reviewReason)
          : await api.rejectUser(user.id, reviewReason);

      if (result.warning) {
        setNotice(`${result.message} Warning: ${result.warning}`);
      } else {
        setNotice(result.message);
      }

      if (decision === "approve") {
        setActiveUsers((current) => {
          const withoutTarget = current.filter((item) => item.id !== result.user.id);
          return [result.user, ...withoutTarget];
        });
      }
    } catch (decisionError) {
      setPendingUsers(snapshot);
      setActiveUsers(activeSnapshot);
      setError(toUserErrorMessage(decisionError));
    } finally {
      setActioningUserId(null);
    }
  }

  async function handleGrantAccess() {
    setError(null);
    setNotice(null);

    const employeeId = normalizeEmployeeId(grantEmployeeId);
    if (!employeeId) {
      setError("Employee ID is required to grant access.");
      return;
    }

    if (!EMPLOYEE_ID_PATTERN.test(employeeId)) {
      setError("Employee ID must be 4-24 characters and can only contain letters, numbers, underscores, or hyphens.");
      return;
    }

    setGranting(true);
    try {
      const result = await api.grantUserAccess(employeeId, grantReason.trim() || undefined);

      setActiveUsers((current) => {
        const withoutTarget = current.filter((item) => item.id !== result.user.id);
        return [result.user, ...withoutTarget];
      });
      setPendingUsers((current) => current.filter((item) => item.id !== result.user.id));

      setGrantEmployeeId("");
      setGrantReason("");

      if (result.warning) {
        setNotice(`${result.message} Warning: ${result.warning}`);
      } else {
        setNotice(result.message);
      }
    } catch (grantError) {
      setError(toUserErrorMessage(grantError));
    } finally {
      setGranting(false);
    }
  }

  async function handleRevokeAccess(entry: AdminUserSummary) {
    setError(null);
    setNotice(null);

    const reviewReason = window.prompt("Optional revoke reason", "")?.trim() || undefined;
    const activeSnapshot = activeUsers;
    setActioningUserId(entry.id);
    setActiveUsers((current) => current.filter((item) => item.id !== entry.id));

    try {
      const result = await api.revokeUserAccess(entry.id, reviewReason);
      if (result.warning) {
        setNotice(`${result.message} Warning: ${result.warning}`);
      } else {
        setNotice(result.message);
      }
    } catch (revokeError) {
      setActiveUsers(activeSnapshot);
      setError(toUserErrorMessage(revokeError));
    } finally {
      setActioningUserId(null);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div>
          <p className="admin-eyebrow">Authenticate Users</p>
          <h1>Pending Access Requests</h1>
          <p>Review new user registrations and take approval actions with immediate status feedback.</p>
        </div>
        <div className="admin-header__actions">
          <button type="button" className="button button--ghost" onClick={() => navigate("/admin/dashboard")}>
            Back to dashboard
          </button>
          <button type="button" className="button button--ghost" onClick={() => void refreshUsers()}>
            Refresh users
          </button>
          <button type="button" className="button" onClick={() => navigate("/admin/uploads")}>
            Upload documents
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

      <section className="admin-panel" aria-label="Grant employee access">
        <div className="upload-progress-head">
          <h2>Grant Employee Access</h2>
        </div>

        <div className="admin-inline-form">
          <label className="field">
            <span>Employee ID</span>
            <input
              value={grantEmployeeId}
              onChange={(event) => setGrantEmployeeId(event.target.value)}
              placeholder="EMP1234"
              maxLength={24}
            />
          </label>

          <label className="field">
            <span>Reason (optional)</span>
            <input
              value={grantReason}
              onChange={(event) => setGrantReason(event.target.value)}
              placeholder="Access validated by admin"
              maxLength={500}
            />
          </label>

          <button type="button" className="button button--primary" onClick={() => void handleGrantAccess()} disabled={granting}>
            {granting ? "Granting..." : "Grant access"}
          </button>
        </div>
      </section>

      <section className="admin-panel" aria-label="Pending users list">
        {loading ? (
          <p className="hint" role="status" aria-live="polite">
            Loading pending requests...
          </p>
        ) : null}

        {!loading && pendingUsers.length === 0 ? (
          <p className="hint" role="status">
            No pending requests right now.
          </p>
        ) : null}

        <ul className="admin-user-list">
          {pendingUsers.map((entry) => {
            const isBusy = actioningUserId === entry.id;
            return (
              <li key={entry.id} className="admin-user-card">
                <div className="admin-user-card__meta">
                  <h2>{entry.full_name}</h2>
                  <p>Employee ID: {entry.employee_id}</p>
                  <p>Email: {entry.email || "Not provided"}</p>
                  <p>Requested: {new Date(entry.created_at).toLocaleString()}</p>
                </div>

                <div className="admin-user-card__actions">
                  <button
                    type="button"
                    className="icon-action icon-action--approve"
                    onClick={() => void handleDecision(entry, "approve")}
                    disabled={isBusy}
                    aria-label={`Approve ${entry.full_name}`}
                  >
                    <span aria-hidden="true">✓</span>
                    <span>Approve</span>
                  </button>
                  <button
                    type="button"
                    className="icon-action icon-action--reject"
                    onClick={() => void handleDecision(entry, "reject")}
                    disabled={isBusy}
                    aria-label={`Reject ${entry.full_name}`}
                  >
                    <span aria-hidden="true">✕</span>
                    <span>Reject</span>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="admin-panel" aria-label="Active employees list">
        <div className="upload-progress-head">
          <h2>Employees With Access</h2>
          <span className="pill">{activeUsers.length} active</span>
        </div>

        {!loading && activeUsers.length === 0 ? (
          <p className="hint" role="status">
            No active employee accounts found.
          </p>
        ) : null}

        <ul className="admin-user-list">
          {activeUsers.map((entry) => {
            const isBusy = actioningUserId === entry.id;
            return (
              <li key={`active-${entry.id}`} className="admin-user-card">
                <div className="admin-user-card__meta">
                  <h2>{entry.full_name}</h2>
                  <p>Employee ID: {entry.employee_id}</p>
                  <p>Email: {entry.email || "Not available"}</p>
                  <p>Approved: {entry.reviewed_at ? new Date(entry.reviewed_at).toLocaleString() : "-"}</p>
                </div>

                <div className="admin-user-card__actions">
                  <button
                    type="button"
                    className="icon-action icon-action--reject"
                    onClick={() => void handleRevokeAccess(entry)}
                    disabled={isBusy}
                    aria-label={`Remove access for ${entry.full_name}`}
                  >
                    <span aria-hidden="true">✕</span>
                    <span>Remove access</span>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
