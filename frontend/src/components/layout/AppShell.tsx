interface AppShellProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onCloseSidebar: () => void;
}

export function AppShell({
  sidebar,
  children,
  sidebarOpen,
  onToggleSidebar,
  onCloseSidebar,
}: AppShellProps) {
  return (
    <div className="shell">
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

      <aside id="chat-sidebar" className={`shell-sidebar ${sidebarOpen ? "is-open" : ""}`}>
        {sidebar}
      </aside>

      {sidebarOpen ? <button className="sidebar-backdrop" onClick={onCloseSidebar} aria-label="Close sidebar" /> : null}

      <main className="shell-main">{children}</main>
    </div>
  );
}
