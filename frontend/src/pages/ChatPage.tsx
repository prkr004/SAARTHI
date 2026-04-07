import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { MessageBubble } from "../components/chat/MessageBubble";
import { MessageComposer } from "../components/chat/MessageComposer";
import { ModelSelector } from "../components/chat/ModelSelector";
import { AppShell } from "../components/layout/AppShell";
import { Sidebar } from "../components/layout/Sidebar";
import { useAuth } from "../hooks/useAuth";
import { api } from "../lib/api/endpoints";
import { ApiClientError } from "../lib/api/client";
import type { ConversationSummary, FrontendMessage, MessageItem, ModelConfig } from "../lib/api/types";
import { toUserErrorMessage } from "../lib/errors";
import { storage } from "../lib/storage";

const DEFAULT_TOP_K = 5;

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

  const [models, setModels] = useState<ModelConfig[]>([]);
  const [selectedModel, setSelectedModel] = useState("");

  const [question, setQuestion] = useState("");
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  const hasMessages = messages.length > 0;

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

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
        const [modelsPayload] = await Promise.all([api.listModels(), hydrateConversations()]);

        if (!active) {
          return;
        }

        setModels(modelsPayload.models);
        const persistedModel = storage.getSelectedModel();
        const modelId = modelsPayload.models.some((model) => model.id === persistedModel)
          ? (persistedModel as string)
          : modelsPayload.recommended_model;
        setSelectedModel(modelId);
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
        model_id: selectedModel,
        top_k: DEFAULT_TOP_K,
        comparison_method: "both",
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

  function handleModelChange(modelId: string) {
    setSelectedModel(modelId);
    storage.setSelectedModel(modelId);
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const welcomePrompts = useMemo(
    () => [
      "What are the key digital lending guidelines?",
      "Explain the KYC requirements for customer due diligence.",
      "How has the latest guidance changed from previous versions?",
      "What is allowed for lending service providers?",
    ],
    [],
  );

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
          onLogout={handleLogout}
        />
      }
    >
      <section className="workspace-header">
        <div>
          <h1>SAARTHI - Regulatory Q&A Assistant</h1>
          <p>
            Ask grounded questions on indexed RBI circulars. Temporal queries are detected automatically for version comparison.
          </p>
        </div>
      </section>

      <ModelSelector
        models={models}
        value={selectedModel}
        loading={loadingWorkspace}
        onChange={handleModelChange}
      />

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

      <section className="chat-surface" aria-label="Chat messages">
        {loadingMessages ? <p className="hint">Loading messages...</p> : null}

        {!loadingMessages && !hasMessages ? (
          <article className="welcome-card">
            <h2>Namaste, {user?.full_name ?? "there"}</h2>
            <p>Start with one of these prompts or ask your own compliance question.</p>
            <ul>
              {welcomePrompts.map((prompt) => (
                <li key={prompt}>
                  <button type="button" onClick={() => setQuestion(prompt)}>
                    {prompt}
                  </button>
                </li>
              ))}
            </ul>
          </article>
        ) : null}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        <div ref={scrollAnchorRef} />
      </section>

      <MessageComposer value={question} disabled={sending || !activeConversationId} onChange={setQuestion} onSubmit={handleSubmitQuestion} />

      <footer className="workspace-footer">
        For informational support only. Validate conclusions against official RBI circulars and qualified compliance advice.
      </footer>
    </AppShell>
  );
}
