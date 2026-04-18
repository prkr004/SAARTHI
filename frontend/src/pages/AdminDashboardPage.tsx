import { useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

interface FeatureCard {
  title: string;
  description: string;
  cta: string;
  path: string;
}

const FEATURE_CARDS: FeatureCard[] = [
  {
    title: "RAG Chatbot",
    description: "Open the same source-grounded chatbot module used by employee users.",
    cta: "Open Chat",
    path: "/admin/chat",
  },
  {
    title: "Document Generator",
    description: "Navigate to the existing drafting module for policy and advisory generation.",
    cta: "Open Generator",
    path: "/admin/drafting",
  },
  {
    title: "Authenticate Users",
    description: "Review pending registrations and approve or reject access requests.",
    cta: "Manage Requests",
    path: "/admin/users",
  },
  {
    title: "Upload Documents",
    description: "Upload multiple PDFs and track ingestion progress into the FAISS index.",
    cta: "Manage Uploads",
    path: "/admin/uploads",
  },
];

export function AdminDashboardPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div>
          <p className="admin-eyebrow">SAARTHI Admin Portal</p>
          <h1>Operations Dashboard</h1>
          <p>
            Approve user access and maintain ingestion freshness while preserving normal user chat and drafting
            experiences.
          </p>
        </div>
        <div className="admin-header__actions">
          <button type="button" className="button button--ghost" onClick={() => navigate("/admin/chat")}>
            Open admin chat
          </button>
          <button
            type="button"
            className="button"
            onClick={() => {
              void logout().then(() => navigate("/admin/login", { replace: true }));
            }}
          >
            Logout
          </button>
        </div>
      </header>

      <section className="admin-summary" aria-label="Admin profile summary">
        <div>
          <span>Signed in as</span>
          <strong>{user?.full_name ?? "Admin"}</strong>
        </div>
        <div>
          <span>Employee ID</span>
          <strong>{user?.employee_id ?? "-"}</strong>
        </div>
        <div>
          <span>Role</span>
          <strong>{user?.role ?? "admin"}</strong>
        </div>
      </section>

      <section className="admin-grid" aria-label="Admin features">
        {FEATURE_CARDS.map((card) => (
          <article key={card.title} className="admin-feature-card">
            <h2>{card.title}</h2>
            <p>{card.description}</p>
            <button
              type="button"
              className="button button--primary"
              onClick={() => navigate(card.path)}
            >
              {card.cta}
            </button>
          </article>
        ))}
      </section>
    </div>
  );
}
