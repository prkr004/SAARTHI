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

  return (
    <div className="sidebar">
      <header className="sidebar-header">
        <h2>Employee Workspace</h2>
        <p>
          {userName} ({employeeId})
        </p>
        <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="Toggle color theme">
          {theme === "dark" ? "Switch to Light" : "Switch to Dark"}
        </button>
      </header>

      <div className="sidebar-actions">
        <button type="button" className="button button--primary" onClick={onCreateConversation}>
          + New Chat
        </button>
        {onOpenSettings ? (
          <button type="button" className="button button--ghost" onClick={onOpenSettings}>
            Settings
          </button>
        ) : null}
      </div>

      <section className="sidebar-section" aria-label="Conversations">
        <details className="sidebar-fold" open>
          <summary>
            <h3>Your Chats</h3>
          </summary>

          {loading ? <p className="hint">Loading chats...</p> : null}
          {!loading && conversations.length === 0 ? <p className="hint">No chats yet.</p> : null}

          <ul className="conversation-list">
            {conversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <li key={conversation.id} className={`conversation-item ${isActive ? "is-active" : ""}`}>
                  <button
                    type="button"
                    className="conversation-open"
                    onClick={() => onSelectConversation(conversation.id)}
                  >
                    {conversation.title || "New Chat"}
                  </button>

                  <div className="conversation-actions">
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => onRenameConversation(conversation.id, conversation.title)}
                      aria-label={`Rename ${conversation.title}`}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="icon-btn danger"
                      onClick={() => onDeleteConversation(conversation.id)}
                      aria-label={`Delete ${conversation.title}`}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </details>
      </section>

      <button type="button" className="button button--ghost" onClick={onLogout}>
        Logout
      </button>
    </div>
  );
}
