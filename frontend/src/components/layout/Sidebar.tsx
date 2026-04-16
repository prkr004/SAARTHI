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

        <button type="button" className="button button--primary button--compact sidebar-new-chat" onClick={onCreateConversation}>
          <span className="new-chat-icon" aria-hidden="true">
            +
          </span>
          <span>New chat</span>
        </button>
      </header>

      <section className="sidebar-section" aria-label="Conversations">
        <div className="sidebar-section__header">
          <h3>Chats</h3>
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
          />
        </label>

        {loading ? <p className="hint">Loading chats...</p> : null}
        {!loading && conversations.length === 0 ? <p className="hint">No chats yet.</p> : null}
        {!loading && hasSearch && filteredConversations.length === 0 ? (
          <p className="hint">No chats match "{searchTerm.trim()}".</p>
        ) : null}

        <ul className="conversation-list">
          {filteredConversations.map((conversation) => {
            const isActive = conversation.id === activeConversationId;
            const title = conversation.title || "New Chat";

            return (
              <li key={conversation.id} className={`conversation-item ${isActive ? "is-active" : ""}`}>
                <button
                  type="button"
                  className="conversation-open"
                  onClick={() => onSelectConversation(conversation.id)}
                  title={title}
                >
                  {title}
                </button>

                <details className="conversation-manage">
                  <summary
                    className="conversation-manage__summary"
                    aria-label={`Conversation actions for ${title}`}
                  >
                    ...
                  </summary>
                  <div className="conversation-menu">
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => onRenameConversation(conversation.id, title)}
                      aria-label={`Rename ${title}`}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="icon-btn danger"
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
            <button type="button" className="button button--ghost button--compact" onClick={onOpenSettings}>
              Settings
            </button>
          ) : null}
          <button type="button" className="button button--ghost button--compact" onClick={onLogout}>
            Logout
          </button>
        </div>
      </footer>
    </div>
  );
}
