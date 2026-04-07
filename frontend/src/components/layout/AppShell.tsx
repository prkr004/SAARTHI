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
      >
        {sidebarOpen ? "Close menu" : "Open menu"}
      </button>

      <aside id="chat-sidebar" className={`shell-sidebar ${sidebarOpen ? "is-open" : ""}`}>
        {sidebar}
      </aside>

      {sidebarOpen ? <button className="sidebar-backdrop" onClick={onCloseSidebar} aria-label="Close sidebar" /> : null}

      <main className="shell-main">{children}</main>
    </div>
  );
}
