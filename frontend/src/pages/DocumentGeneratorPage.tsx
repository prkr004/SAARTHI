import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { AppShell } from "../components/layout/AppShell";
import { Sidebar } from "../components/layout/Sidebar";
import { useAuth } from "../hooks/useAuth";
import { ApiClientError } from "../lib/api/client";
import { api } from "../lib/api/endpoints";
import type { ConversationSummary, GenerateDocumentRequest } from "../lib/api/types";
import { toUserErrorMessage } from "../lib/errors";
import { storage } from "../lib/storage";

type DocumentType = GenerateDocumentRequest["document_type"];

const DOCUMENT_TYPES: Array<{ value: DocumentType; label: string; description: string }> = [
  { value: "circular", label: "Circular", description: "Internal branch communication with clear action items." },
  { value: "press_release", label: "Press Release", description: "External communication for public announcements." },
  { value: "advisory", label: "Advisory", description: "Compliance guidance and employee instructions." },
];

function parseFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) {
    return fallback;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const simpleMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return simpleMatch?.[1] ?? fallback;
}

export function DocumentGeneratorPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const isAdminPortal = location.pathname.startsWith("/admin");
  const chatRoute = isAdminPortal ? "/admin/chat" : "/";
  const draftingRoute = isAdminPortal ? "/admin/drafting" : "/drafting";
  const settingsRoute = isAdminPortal ? "/admin/dashboard" : "/settings";
  const profileRoute = isAdminPortal ? "/admin/profile" : "/profile";
  const loginRoute = isAdminPortal ? "/admin/login" : "/login";
  const userScope = isAdminPortal ? "admin" : "employee";
  const storedDisplayName = storage.getDisplayName(userScope);
  const userDisplayName = storedDisplayName?.trim() || user?.full_name || "Employee";

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [documentType, setDocumentType] = useState<DocumentType>("circular");
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState("internal");

  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadFilename, setDownloadFilename] = useState("saarthi-document.docx");

  const selectedTemplate = useMemo(
    () => DOCUMENT_TYPES.find((item) => item.value === documentType) ?? DOCUMENT_TYPES[0],
    [documentType],
  );

  useEffect(() => {
    let active = true;

    async function loadWorkspace() {
      setLoadingWorkspace(true);
      try {
        const nextConversations = await api.listConversations();
        if (!active) {
          return;
        }
        setConversations(nextConversations);
      } catch (workspaceError) {
        if (!active) {
          return;
        }
        setError(toUserErrorMessage(workspaceError));
      } finally {
        if (active) {
          setLoadingWorkspace(false);
        }
      }
    }

    loadWorkspace();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (downloadUrl) {
        window.URL.revokeObjectURL(downloadUrl);
      }
    };
  }, [downloadUrl]);

  async function handleGenerate() {
    const trimmedQuery = query.trim();
    const trimmedAudience = audience.trim() || "internal";

    if (!trimmedQuery) {
      setError("Enter a topic or query before generating a document.");
      return;
    }

    setGenerating(true);
    setError(null);
    setNotice(null);

    try {
      const response = await api.generateDocument({
        document_type: documentType,
        query: trimmedQuery,
        audience: trimmedAudience,
      });

      const blob = await response.blob();
      const nextUrl = window.URL.createObjectURL(blob);
      const filename = parseFilename(
        response.headers.get("content-disposition"),
        `${documentType}-${trimmedQuery.slice(0, 24).replace(/\s+/g, "-").toLowerCase() || "document"}.docx`,
      );

      if (downloadUrl) {
        window.URL.revokeObjectURL(downloadUrl);
      }

      setDownloadUrl(nextUrl);
      setDownloadFilename(filename);
      setNotice("Document generated and ready for download.");
    } catch (generateError) {
      const message = generateError instanceof ApiClientError ? generateError.message : toUserErrorMessage(generateError);
      setError(message);
      setDownloadUrl(null);
    } finally {
      setGenerating(false);
    }
  }

  function handleDownload() {
    if (!downloadUrl) {
      return;
    }

    const anchor = document.createElement("a");
    anchor.href = downloadUrl;
    anchor.download = downloadFilename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  return (
    <AppShell
      sidebar={
        <Sidebar
          userName={userDisplayName}
          employeeId={user?.employee_id ?? "-"}
          conversations={conversations}
          activeConversationId={null}
          loading={loadingWorkspace}
          onSelectConversation={() => navigate(chatRoute)}
          onCreateConversation={() => navigate(chatRoute)}
          onRenameConversation={() => navigate(chatRoute)}
          onDeleteConversation={() => navigate(chatRoute)}
          onOpenDrafting={() => navigate(draftingRoute)}
          onOpenSettings={() => navigate(settingsRoute)}
          onOpenProfile={() => navigate(profileRoute)}
          onLogout={() => {
            void logout().then(() => navigate(loginRoute, { replace: true }));
          }}
        />
      }
      sidebarOpen={sidebarOpen}
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarOpen((current) => !current)}
      onCloseSidebar={() => setSidebarOpen(false)}
      onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
    >
      <div className="drafting-stage">
        <header className="drafting-header">
          <div>
            <p className="drafting-eyebrow">Document Generator</p>
            <h1>Generate banking documents from regulatory context</h1>
            <p>
              Draft a circular, press release, or advisory from retrieved regulatory material using a controlled
              structured workflow.
            </p>
          </div>

          <div className="drafting-header__actions">
            <button type="button" className="button button--ghost" onClick={() => navigate(chatRoute)}>Back to chat</button>
            <button type="button" className="button" onClick={() => navigate(settingsRoute)}>{isAdminPortal ? "Back to admin" : "Workspace settings"}</button>
          </div>
        </header>

        <div className="drafting-grid">
          <section className="drafting-card" aria-label="Document setup">
            <h2>Document Setup</h2>
            <p>Choose a format and provide the topic you want the document to cover.</p>

            <label className="field">
              <span>Document type</span>
              <select value={documentType} onChange={(event) => setDocumentType(event.target.value as DocumentType)}>
                {DOCUMENT_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <p className="drafting-card__hint">{selectedTemplate.description}</p>

            <label className="field">
              <span>Topic / query</span>
              <textarea
                rows={5}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Example: KYC update 2025"
              />
            </label>

            <label className="field">
              <span>Audience</span>
              <input
                type="text"
                value={audience}
                onChange={(event) => setAudience(event.target.value)}
                placeholder="internal"
              />
            </label>

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

            <div className="drafting-actions">
              <button type="button" className="button button--primary" onClick={handleGenerate} disabled={generating}>
                {generating ? "Generating..." : "Generate document"}
              </button>
              <button type="button" className="button" onClick={handleDownload} disabled={!downloadUrl || generating}>
                Download DOCX
              </button>
            </div>
          </section>

          <section className="drafting-card drafting-card--preview" aria-label="Drafting preview">
            <h2>Drafting Preview</h2>
            <p>This first version keeps the workflow simple: generate first, then download the Word file.</p>

            <div className="drafting-preview">
              <div>
                <span>Type</span>
                <strong>{selectedTemplate.label}</strong>
              </div>
              <div>
                <span>Topic</span>
                <strong>{query.trim() || "Not entered yet"}</strong>
              </div>
              <div>
                <span>Audience</span>
                <strong>{audience.trim() || "internal"}</strong>
              </div>
              <div>
                <span>Status</span>
                <strong>{downloadUrl ? "Ready to download" : generating ? "Generating" : "Idle"}</strong>
              </div>
            </div>

            <ul className="drafting-checklist">
              <li>Structured JSON drafting flow</li>
              <li>Backend RAG and temporal comparison</li>
              <li>Word export with banking-style formatting</li>
            </ul>
          </section>
        </div>
      </div>
    </AppShell>
  );
}