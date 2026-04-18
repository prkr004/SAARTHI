import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api/endpoints";
import type { AdminUserSummary } from "../lib/api/types";
import { toUserErrorMessage } from "../lib/errors";

export function AdminUserApprovalPage() {
  const navigate = useNavigate();

  const [pendingUsers, setPendingUsers] = useState<AdminUserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [actioningUserId, setActioningUserId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadPendingUsers() {
      setLoading(true);
      setError(null);
      try {
        const rows = await api.listPendingUsers();
        if (!active) {
          return;
        }
        setPendingUsers(rows);
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
    setPendingUsers((current) => current.filter((item) => item.id !== user.id));
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
    } catch (decisionError) {
      setPendingUsers(snapshot);
      setError(toUserErrorMessage(decisionError));
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
    </div>
  );
}
