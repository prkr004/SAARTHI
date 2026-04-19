import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { MessageBubble } from "../components/chat/MessageBubble";
import { MessageComposer } from "../components/chat/MessageComposer";
import { AppShell } from "../components/layout/AppShell";
import { Sidebar } from "../components/layout/Sidebar";
import { useAuth } from "../hooks/useAuth";
import { api } from "../lib/api/endpoints";
import { ApiClientError } from "../lib/api/client";
import type { ConversationSummary, FrontendMessage, MessageItem } from "../lib/api/types";
import { toUserErrorMessage } from "../lib/errors";
import { getWorkspacePreferences } from "../lib/preferences";
import { storage } from "../lib/storage";

const STARTER_CHIPS = [
  {
    label: "Digital Lending Obligations",
    full: "Summarize key obligations for digital lending apps under RBI guidelines.",
  },
  {
    label: "Pre-Disbursal Disclosures",
    full: "What disclosures are mandatory before loan disbursal in digital lending?",
  },
  {
    label: "LSP Restrictions",
    full: "What restrictions apply to lending service providers in RBI guidance?",
  },
  {
    label: "First-Time Loan Onboarding",
    full: "List compliance checkpoints for first-time digital loan onboarding.",
  },
  {
    label: "KYC Due Diligence Steps",
    full: "Explain customer due diligence steps under the RBI KYC Master Direction.",
  },
  {
    label: "Enhanced Due Diligence",
    full: "When is enhanced due diligence required for customer onboarding?",
  },
  {
    label: "KYC Record Retention",
    full: "What are KYC record retention requirements and timelines?",
  },
  {
    label: "Borrower Consent Changes",
    full: "How did the latest digital lending circular change borrower consent requirements?",
  },
  {
    label: "2022 vs Latest Cooling-Off",
    full: "Compare 2022 vs latest guidance on cooling-off period obligations.",
  },
  {
    label: "Grievance Redressal Changes",
    full: "What changed in grievance redressal expectations across versions?",
  },
  {
    label: "DPDP & RBI Intersection",
    full: "How does DPDP 2023 intersect with RBI digital lending compliance?",
  },
  {
    label: "Data Minimization",
    full: "What data minimization practices are expected in lending workflows?",
  },
] as const;

function createMessageId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `msg-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
}

function toFrontendMessage(message: MessageItem): FrontendMessage {
  return {
    id: createMessageId(),
    role: message.role,
    content: message.content,
    sources: message.sources ?? [],
  };
}

export function ChatPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const isAdminPortal = location.pathname.startsWith("/admin");
  const loginRoute = isAdminPortal ? "/admin/login" : "/login";
  const draftingRoute = isAdminPortal ? "/admin/drafting" : "/drafting";
  const settingsRoute = isAdminPortal ? "/admin/dashboard" : "/settings";
  const profileRoute = isAdminPortal ? "/admin/profile" : "/profile";
  const userScope = isAdminPortal ? "admin" : "employee";
  const storedDisplayName = storage.getDisplayName(userScope);
  const userDisplayName = storedDisplayName?.trim() || user?.full_name || "Employee";

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<FrontendMessage[]>([]);

  const [selectedModel, setSelectedModel] = useState<string>(() => storage.getSelectedModel() ?? "");
  const [preferences, setPreferences] = useState(() => getWorkspacePreferences());

  const [question, setQuestion] = useState("");
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [promptLibraryOpen, setPromptLibraryOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const stopRequestedRef = useRef(false);

  const hasMessages = messages.length > 0;
  const showHomeState = !loadingMessages && !hasMessages;

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    function refreshPreferences() {
      setPreferences(getWorkspacePreferences());
      setSelectedModel(storage.getSelectedModel() ?? "");
    }

    window.addEventListener("focus", refreshPreferences);
    return () => window.removeEventListener("focus", refreshPreferences);
  }, []);

  async function hydrateConversations(preferredConversationId?: number) {
    let nextConversations = await api.listConversations();

    if (nextConversations.length === 0) {
      await api.ensureDefaultConversation();
      nextConversations = await api.listConversations();
    }

    setConversations(nextConversations);

    if (nextConversations.length === 0) {
      setActiveConversationId(null);
      return;
    }

    if (preferredConversationId) {
      const exists = nextConversations.some((conversation) => conversation.id === preferredConversationId);
      if (exists) {
        setActiveConversationId(preferredConversationId);
        return;
      }
    }

    setActiveConversationId((current) => {
      if (current && nextConversations.some((conversation) => conversation.id === current)) {
        return current;
      }
      return nextConversations[0].id;
    });
  }

  useEffect(() => {
    let active = true;

    async function bootstrapWorkspace() {
      setLoadingWorkspace(true);
      setError(null);

      try {
        await hydrateConversations();

        if (!active) {
          return;
        }
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

    bootstrapWorkspace();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadMessages() {
      if (!activeConversationId) {
        setMessages([]);
        return;
      }

      setLoadingMessages(true);
      setError(null);

      try {
        const payload = await api.listMessages(activeConversationId);
        if (!active) {
          return;
        }
        setMessages(payload.map(toFrontendMessage));
      } catch (messageError) {
        if (!active) {
          return;
        }
        setError(toUserErrorMessage(messageError));
      } finally {
        if (active) {
          setLoadingMessages(false);
        }
      }
    }

    loadMessages();

    return () => {
      active = false;
    };
  }, [activeConversationId]);

  async function handleCreateConversation() {
    try {
      setNotice(null);
      const created = await api.createConversation("New Chat");
      await hydrateConversations(created.id);
      setMessages([]);
      setSidebarOpen(false);
    } catch (createError) {
      setError(toUserErrorMessage(createError));
    }
  }

  async function handleRenameConversation(conversationId: number, currentTitle: string) {
    const nextTitle = window.prompt("Rename chat", currentTitle || "New Chat");
    if (!nextTitle || !nextTitle.trim()) {
      return;
    }

    try {
      await api.renameConversation(conversationId, nextTitle.trim());
      await hydrateConversations(conversationId);
      setNotice("Chat renamed.");
    } catch (renameError) {
      setError(toUserErrorMessage(renameError));
    }
  }

  async function handleDeleteConversation(conversationId: number) {
    const confirmed = window.confirm("Delete this conversation permanently?");
    if (!confirmed) {
      return;
    }

    try {
      await api.deleteConversation(conversationId);
      await hydrateConversations();
      setNotice("Chat deleted.");
    } catch (deleteError) {
      setError(toUserErrorMessage(deleteError));
    }
  }

  function handleOpenDrafting() {
    navigate(draftingRoute);
  }

  async function handleSubmitQuestion(overrideQuestion?: string) {
    if (!activeConversationId || sending) {
      return;
    }

    const trimmedQuestion = (overrideQuestion ?? question).trim();
    if (!trimmedQuestion) {
      return;
    }

    setError(null);
    setNotice(null);
    setQuestion("");
    stopRequestedRef.current = false;

    const userMessage: FrontendMessage = {
      id: createMessageId(),
      role: "user",
      content: trimmedQuestion,
      sources: [],
      pending: true,
    };

    setMessages((previous) => [...previous, userMessage]);
    setSending(true);

    try {
      await api.addMessage(activeConversationId, {
        role: "user",
        content: trimmedQuestion,
        sources: [],
      });

      const response = await api.askTemporal({
        question: trimmedQuestion,
        model_id: selectedModel || undefined,
        top_k: preferences.topK,
        comparison_method: preferences.comparisonMethod,
      });

      if (stopRequestedRef.current) {
        return;
      }

      const assistantSources = response.formatted_sources.length > 0 ? response.formatted_sources : response.sources;
      const assistantMessage: FrontendMessage = {
        id: createMessageId(),
        role: "assistant",
        content: response.answer,
        sources: assistantSources,
        mode: response.mode,
        temporal: response.temporal,
      };

      setMessages((previous) =>
        previous.map((message) => (message.id === userMessage.id ? { ...message, pending: false } : message)).concat(assistantMessage),
      );

      await api.addMessage(activeConversationId, {
        role: "assistant",
        content: response.answer,
        sources: assistantSources,
      });
      await hydrateConversations(activeConversationId);
    } catch (sendError) {
      if (stopRequestedRef.current) {
        return;
      }

      const message = toUserErrorMessage(sendError);
      setMessages((previous) => [
        ...previous.map((entry) => (entry.id === userMessage.id ? { ...entry, pending: false } : entry)),
        {
          id: createMessageId(),
          role: "assistant",
          content: message,
          sources: [],
        },
      ]);

      if (sendError instanceof ApiClientError && sendError.status === 401) {
        await logout();
        navigate(loginRoute, { replace: true });
      } else {
        setError(message);
      }
    } finally {
      setSending(false);
    }
  }

  function handleStop() {
    stopRequestedRef.current = true;
    setSending(false);
    setMessages((previous) => previous.filter((message) => !message.pending));
  }

  async function handleEditMessage(messageId: string, newContent: string) {
    if (!newContent.trim()) {
      return;
    }

    setMessages((previous) => {
      const index = previous.findIndex((message) => message.id === messageId);
      if (index === -1) {
        return previous;
      }
      return previous.slice(0, index);
    });

    await handleSubmitQuestion(newContent);
  }

  async function handleLogout() {
    await logout();
    navigate(loginRoute, { replace: true });
  }

  return (
    <AppShell
      sidebarOpen={sidebarOpen}
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarOpen((current) => !current)}
      onCloseSidebar={() => setSidebarOpen(false)}
      onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
      sidebar={
        <Sidebar
          userName={userDisplayName}
          conversations={conversations}
          activeConversationId={activeConversationId}
          loading={loadingWorkspace}
          onSelectConversation={(conversationId) => {
            setActiveConversationId(conversationId);
            setSidebarOpen(false);
          }}
          onCreateConversation={handleCreateConversation}
          onRenameConversation={handleRenameConversation}
          onDeleteConversation={handleDeleteConversation}
          onOpenDrafting={handleOpenDrafting}
          onOpenSettings={() => {
            setSidebarOpen(false);
            navigate(settingsRoute);
          }}
          onOpenProfile={() => {
            setSidebarOpen(false);
            navigate(profileRoute);
          }}
          onLogout={handleLogout}
        />
      }
    >
      {!showHomeState ? (
        <header className="workspace-header workspace-header--minimal">
          <h1>SAARTHI</h1>
        </header>
      ) : null}

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

      <section
        className={`chat-surface ${preferences.compactChat ? "is-compact" : ""} ${showHomeState ? "chat-surface--home" : "chat-surface--conversation"}`}
        aria-label="Chat messages"
        aria-busy={loadingMessages || sending}
      >
        {loadingMessages ? (
          <p className="hint hint--loading" role="status" aria-live="polite">
            Loading conversation...
          </p>
        ) : null}

        {showHomeState ? (
          <article className="home-stage" aria-label="SAARTHI home">
            <div className="home-stage-topbar">
              <button
                type="button"
                className="prompt-library-trigger"
                onClick={() => setPromptLibraryOpen(true)}
              >
                Prompt Library
              </button>
            </div>

            <p className="home-stage__eyebrow">Namaste, {userDisplayName || "there"}</p>
            <h2>What should SAARTHI help you review today?</h2>
            <p className="home-stage__subtext">
              Ask about RBI circulars, KYC controls, digital lending obligations, or temporal clause changes.
            </p>

            <div className="home-composer" aria-label="Ask SAARTHI">
              <MessageComposer
                value={question}
                disabled={sending || !activeConversationId}
                isBusy={sending}
                onChange={setQuestion}
                onSubmit={handleSubmitQuestion}
                context="home"
              />
            </div>

            <section className="home-prompts" aria-label="Suggested prompts">
              <h3>Suggested starters</h3>
              <ul className="prompt-chips">
                {STARTER_CHIPS.slice(0, 4).map((chip) => (
                  <li key={chip.label}>
                    <button type="button" className="prompt-chip" onClick={() => void handleSubmitQuestion(chip.full)}>
                      {chip.label}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </article>
        ) : null}

        {!showHomeState ? (
          <div className="chat-feed chat-feed--conversation" aria-live="polite">
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                showTemporal={preferences.showTemporalDetails}
                compactSources={!preferences.showSourceSnippets}
                onEdit={handleEditMessage}
              />
            ))}

            {sending ? (
              <article className="message message--assistant message--loading" role="status" aria-live="polite">
                <header className="message-head">
                  <div className="message-head__identity">
                    <strong className="message-author">SAARTHI</strong>
                  </div>
                  <span className="mode-tag">Processing</span>
                </header>
                <div className="typing-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="message-body">
                  <p className="message-text">Reviewing indexed circulars and preparing a grounded response...</p>
                </div>
              </article>
            ) : null}
          </div>
        ) : null}

        <div ref={scrollAnchorRef} />
      </section>

      {promptLibraryOpen ? (
        <div className="prompt-library-overlay" onClick={() => setPromptLibraryOpen(false)}>
          <div className="prompt-library-panel" onClick={(event) => event.stopPropagation()}>
            <div className="prompt-library-header">
              <h3>Prompt Library</h3>
              <button type="button" className="prompt-library-close" onClick={() => setPromptLibraryOpen(false)}>
                x
              </button>
            </div>
            <div className="prompt-library-scroll">
              {STARTER_CHIPS.map((chip) => (
                <button
                  key={chip.label}
                  type="button"
                  className="prompt-library-item"
                  onClick={() => {
                    setPromptLibraryOpen(false);
                    void handleSubmitQuestion(chip.full);
                  }}
                >
                  <span className="prompt-library-item__label">{chip.label}</span>
                  <span className="prompt-library-item__full">{chip.full}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {!showHomeState ? (
        <div className="composer-dock composer-dock--conversation">
          <MessageComposer
            value={question}
            disabled={!activeConversationId}
            isBusy={sending}
            onChange={setQuestion}
            onSubmit={handleSubmitQuestion}
            onStop={handleStop}
            context="conversation"
          />
        </div>
      ) : null}

      {!showHomeState ? (
        <footer className="workspace-footer">
          For informational support only. Validate conclusions against official RBI circulars and qualified compliance advice.
        </footer>
      ) : null}
    </AppShell>
  );
}
