import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

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

const PROMPT_GROUPS = [
  {
    title: "Digital Lending",
    prompts: [
      "Summarize key obligations for digital lending apps under RBI guidelines.",
      "What disclosures are mandatory before loan disbursal in digital lending?",
      "What restrictions apply to lending service providers in RBI guidance?",
      "List compliance checkpoints for first-time digital loan onboarding.",
    ],
  },
  {
    title: "KYC & Due Diligence",
    prompts: [
      "Explain customer due diligence steps under the RBI KYC Master Direction.",
      "When is enhanced due diligence required for customer onboarding?",
      "What are KYC record retention requirements and timelines?",
      "What red flags should trigger periodic KYC review escalation?",
    ],
  },
  {
    title: "Temporal Comparison",
    prompts: [
      "How did the latest digital lending circular change borrower consent requirements?",
      "Compare 2022 vs latest guidance on cooling-off period obligations.",
      "What changed in grievance redressal expectations across versions?",
      "Which clauses were tightened in the latest circular compared to previous one?",
    ],
  },
  {
    title: "Data Protection",
    prompts: [
      "How does DPDP 2023 intersect with RBI digital lending compliance?",
      "What data minimization practices are expected in lending workflows?",
      "What should be included in consent notices for personal data processing?",
      "What are safe defaults for storing customer KYC and lending records?",
    ],
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
  const { user, logout } = useAuth();

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
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  const hasMessages = messages.length > 0;
  const showHomeState = !loadingMessages && !hasMessages;
  const featuredPrompts = useMemo(
    () => PROMPT_GROUPS.flatMap((group) => group.prompts).slice(0, 4),
    [],
  );

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

  async function handleSubmitQuestion() {
    if (!activeConversationId || sending) {
      return;
    }

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      return;
    }

    setError(null);
    setNotice(null);
    setQuestion("");

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
        navigate("/login", { replace: true });
      } else {
        setError(message);
      }
    } finally {
      setSending(false);
    }
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AppShell
      sidebarOpen={sidebarOpen}
      onToggleSidebar={() => setSidebarOpen((current) => !current)}
      onCloseSidebar={() => setSidebarOpen(false)}
      sidebar={
        <Sidebar
          userName={user?.full_name ?? "Employee"}
          employeeId={user?.employee_id ?? "-"}
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
          onOpenSettings={() => {
            setSidebarOpen(false);
            navigate("/settings");
          }}
          onLogout={handleLogout}
        />
      }
    >
      <section className={`workspace-header ${showHomeState ? "workspace-header--calm" : ""}`}>
        <div className="workspace-header__top">
          <div>
            <h1>SAARTHI Chat Workspace</h1>
            <p>Source-grounded compliance guidance with focused, conversational navigation.</p>
          </div>
        </div>

        {!showHomeState ? (
          <div className="workspace-kpis" aria-label="Current session profile">
            <span className="stat-chip">Top-K {preferences.topK}</span>
            <span className="stat-chip">Compare: {preferences.comparisonMethod}</span>
            <span className="stat-chip">Model: {selectedModel || "Auto"}</span>
            <span className="stat-chip">Mode: {preferences.compactChat ? "Compact" : "Comfort"}</span>
          </div>
        ) : null}
      </section>

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
      >
        {loadingMessages ? <p className="hint">Loading messages...</p> : null}

        {showHomeState ? (
          <article className="home-stage" aria-label="SAARTHI home">
            <p className="home-stage__eyebrow">Namaste, {user?.full_name ?? "there"}</p>
            <h2>What should SAARTHI help you review today?</h2>
            <p className="home-stage__subtext">
              Ask about RBI circulars, KYC controls, digital lending obligations, or temporal clause changes.
            </p>

            <div className="home-composer" aria-label="Ask SAARTHI">
              <MessageComposer
                value={question}
                disabled={sending || !activeConversationId}
                onChange={setQuestion}
                onSubmit={handleSubmitQuestion}
                context="home"
              />
            </div>

            <section className="home-prompts" aria-label="Suggested prompts">
              <h3>Suggested starters</h3>
              <ul className="prompt-chips">
                {featuredPrompts.map((prompt) => (
                  <li key={prompt}>
                    <button type="button" className="prompt-chip" onClick={() => setQuestion(prompt)}>
                      {prompt}
                    </button>
                  </li>
                ))}
              </ul>

              <details className="prompt-library">
                <summary>Browse full prompt library</summary>
                <div className="prompt-grid">
                  {PROMPT_GROUPS.map((group) => (
                    <section key={group.title} className="prompt-group">
                      <h3>{group.title}</h3>
                      <ul>
                        {group.prompts.map((prompt) => (
                          <li key={prompt}>
                            <button type="button" className="prompt-chip" onClick={() => setQuestion(prompt)}>
                              {prompt}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              </details>
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

      {!showHomeState ? (
        <div className="composer-dock composer-dock--conversation">
          <MessageComposer
            value={question}
            disabled={sending || !activeConversationId}
            onChange={setQuestion}
            onSubmit={handleSubmitQuestion}
            context="conversation"
          />
        </div>
      ) : null}

      <footer className="workspace-footer">
        For informational support only. Validate conclusions against official RBI circulars and qualified compliance advice.
      </footer>
    </AppShell>
  );
}
