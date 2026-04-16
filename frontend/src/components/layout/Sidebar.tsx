import { useMemo, useState } from "react";

import type { ConversationSummary } from "../../lib/api/types";
import { useTheme } from "../../hooks/useTheme";

interface SidebarProps {
  userName: string;
  employeeId: string;
  conversations: ConversationSummary[];
  activeConversationId: number | null;
  loading: boolean;
  onSelectConversation: (conversationId: number) => void;
  onCreateConversation: () => void;
  onRenameConversation: (conversationId: number, currentTitle: string) => void;
  onDeleteConversation: (conversationId: number) => void;
  onOpenSettings?: () => void;
  onLogout: () => void;
}

export function Sidebar({
  userName,
  employeeId,
  conversations,
  activeConversationId,
  loading,
  onSelectConversation,
  onCreateConversation,
  onRenameConversation,
  onDeleteConversation,
  onOpenSettings,
  onLogout,
}: SidebarProps) {
  const { theme, toggleTheme } = useTheme();
  const [searchTerm, setSearchTerm] = useState("");

  const normalizedSearch = searchTerm.trim().toLowerCase();
  const filteredConversations = useMemo(() => {
    if (!normalizedSearch) {
      return conversations;
    }

    return conversations.filter((conversation) => {
      const title = (conversation.title || "New Chat").toLowerCase();
      return title.includes(normalizedSearch);
    });
  }, [conversations, normalizedSearch]);

  const hasSearch = normalizedSearch.length > 0;

  return (
    <div className="sidebar">
      <header className="sidebar-brand" aria-label="Workspace navigation">
        <div className="sidebar-brand__row">
          <div className="sidebar-badge" aria-hidden="true">
            SA
          </div>
          <div className="sidebar-brand__label">
            <h2>SAARTHI</h2>
            <p>Regulatory Workspace</p>
          </div>
          <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="Toggle color theme">
            {theme === "dark" ? "Light" : "Dark"}
          </button>
        </div>

        <button
          type="button"
          className="button button--primary button--compact sidebar-new-chat sidebar-touch-target"
          onClick={onCreateConversation}
        >
          <span className="new-chat-icon" aria-hidden="true">
            +
          </span>
          <span>New chat</span>
        </button>
      </header>

      <section className="sidebar-section" aria-label="Conversations">
        <div className="sidebar-section__header">
          <h3 id="sidebar-chats-heading">Chats</h3>
          <span className="sidebar-count">{conversations.length}</span>
        </div>

        <label className="sidebar-search-wrap">
          <span className="sr-only">Search conversations</span>
          <input
            type="search"
            className="sidebar-search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search chats"
            autoComplete="off"
          />
        </label>

        {loading ? (
          <p className="hint" role="status" aria-live="polite">
            Loading chats...
          </p>
        ) : null}
        {!loading && conversations.length === 0 ? (
          <p className="hint" role="status" aria-live="polite">
            No chats yet.
          </p>
        ) : null}
        {!loading && hasSearch && filteredConversations.length === 0 ? (
          <p className="hint" role="status" aria-live="polite">
            No chats match "{searchTerm.trim()}".
          </p>
        ) : null}

        <ul className="conversation-list" aria-labelledby="sidebar-chats-heading">
          {filteredConversations.map((conversation) => {
            const isActive = conversation.id === activeConversationId;
            const title = conversation.title || "New Chat";

            return (
              <li key={conversation.id} className={`conversation-item ${isActive ? "is-active" : ""}`}>
                <button
                  type="button"
                  className="conversation-open sidebar-touch-target"
                  onClick={() => onSelectConversation(conversation.id)}
                  title={title}
                  aria-current={isActive ? "page" : undefined}
                >
                  {title}
                </button>

                <details className="conversation-manage">
                  <summary
                    className="conversation-manage__summary"
                    aria-label={`Conversation actions for ${title}`}
                    aria-haspopup="menu"
                  >
                    <span aria-hidden="true">...</span>
                  </summary>
                  <div className="conversation-menu" role="group" aria-label={`Actions for ${title}`}>
                    <button
                      type="button"
                      className="icon-btn sidebar-touch-target"
                      onClick={() => onRenameConversation(conversation.id, title)}
                      aria-label={`Rename ${title}`}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="icon-btn danger sidebar-touch-target"
                      onClick={() => onDeleteConversation(conversation.id)}
                      aria-label={`Delete ${title}`}
                    >
                      Delete
                    </button>
                  </div>
                </details>
              </li>
            );
          })}
        </ul>
      </section>

      <footer className="sidebar-footer">
        <div className="sidebar-account">
          <p className="sidebar-account__name">{userName}</p>
          <p className="sidebar-account__id">Employee ID: {employeeId}</p>
        </div>

        <div className="sidebar-actions">
          {onOpenSettings ? (
            <button
              type="button"
              className="button button--ghost button--compact sidebar-touch-target"
              onClick={onOpenSettings}
            >
              Settings
            </button>
          ) : null}
          <button type="button" className="button button--ghost button--compact sidebar-touch-target" onClick={onLogout}>
            Logout
          </button>
        </div>
      </footer>
    </div>
  );
}
