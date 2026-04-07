import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="center-shell">
      <section className="loading-card">
        <h1>Page not found</h1>
        <p>The route you requested does not exist in this workspace.</p>
        <Link to="/">Go to workspace</Link>
      </section>
    </main>
  );
}
