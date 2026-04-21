import { useEffect } from "react";

interface AppShellProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
  sidebarOpen: boolean;
  sidebarCollapsed?: boolean;
  mainClassName?: string;
  onToggleSidebar: () => void;
  onCloseSidebar: () => void;
  onToggleCollapse?: () => void;
}

export function AppShell({
  sidebar,
  children,
  sidebarOpen,
  sidebarCollapsed = false,
  mainClassName,
  onToggleSidebar,
  onCloseSidebar,
  onToggleCollapse,
}: AppShellProps) {
  useEffect(() => {
    if (!sidebarOpen) {
      return;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCloseSidebar();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onCloseSidebar, sidebarOpen]);

  useEffect(() => {
    if (!sidebarOpen) {
      return;
    }

    if (!window.matchMedia("(max-width: 960px)").matches) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [sidebarOpen]);

  return (
    <div className={`shell ${sidebarCollapsed ? "shell--sidebar-collapsed" : ""}`}>
      <button
        className="mobile-sidebar-toggle"
        type="button"
        onClick={onToggleSidebar}
        aria-expanded={sidebarOpen}
        aria-controls="chat-sidebar"
        aria-label={sidebarOpen ? "Close chat sidebar" : "Open chat sidebar"}
      >
        <span className="mobile-sidebar-toggle__icon" aria-hidden="true">
          =
        </span>
        <span>{sidebarOpen ? "Close" : "Chats"}</span>
      </button>

      <aside id="chat-sidebar" className={`shell-sidebar ${sidebarOpen ? "is-open" : ""}`} aria-label="Chat sidebar">
        {sidebar}
      </aside>

      {onToggleCollapse ? (
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={onToggleCollapse}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? "›" : "‹"}
        </button>
      ) : null}

      <button
        className={`sidebar-backdrop ${sidebarOpen ? "is-open" : ""}`}
        onClick={onCloseSidebar}
        aria-label="Close sidebar"
        aria-hidden={!sidebarOpen}
        tabIndex={sidebarOpen ? 0 : -1}
      />

      <main className={`shell-main ${mainClassName ?? ""}`.trim()} aria-label="Main workspace">
        {children}
      </main>
    </div>
  );
}
