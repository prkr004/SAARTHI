import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { storage, type AuthScope } from "../lib/storage";

export function ProfilePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();

  const isAdminPortal = location.pathname.startsWith("/admin");
  const scope: AuthScope = isAdminPortal ? "admin" : "employee";
  const chatRoute = isAdminPortal ? "/admin/chat" : "/";

  const accountName = user?.full_name ?? "Employee";
  const [displayName, setDisplayName] = useState(accountName);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const storedDisplayName = storage.getDisplayName(scope);
    setDisplayName(storedDisplayName?.trim() || accountName);
  }, [accountName, scope]);

  function handleSaveDisplayName() {
    const trimmed = displayName.trim();
    if (!trimmed) {
      setError("Display name cannot be empty.");
      setNotice(null);
      return;
    }

    storage.setDisplayName(trimmed, scope);
    setError(null);
    setNotice("Display name updated.");
  }

  return (
    <div className="settings-stage">
      <header className="settings-header">
        <button type="button" className="button button--ghost" onClick={() => navigate(chatRoute)}>
          Back to Chat
        </button>
        <div>
          <h1>My Profile</h1>
          <p>Update the name shown in the sidebar and chat greeting.</p>
        </div>
      </header>

      <div className="settings-grid">
        <section className="settings-card" aria-label="Profile details">
          <h2>Display Name</h2>
          <p>Only your workspace display name is editable here.</p>

          <label className="field">
            <span>Display name</span>
            <input
              type="text"
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value);
                if (error) {
                  setError(null);
                }
              }}
              placeholder="Enter display name"
              maxLength={80}
            />
          </label>

          <p className="hint">Account name: {accountName}</p>

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

          <div className="settings-actions">
            <button type="button" className="button button--primary" onClick={handleSaveDisplayName}>
              Save display name
            </button>
            <button
              type="button"
              className="button"
              onClick={() => {
                storage.clearDisplayName(scope);
                setDisplayName(accountName);
                setError(null);
                setNotice("Display name reset to account name.");
              }}
            >
              Reset
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}