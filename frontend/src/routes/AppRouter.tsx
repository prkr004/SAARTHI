import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { ChatPage } from "../pages/ChatPage.tsx";
import { LoginPage } from "../pages/LoginPage.tsx";
import { NotFoundPage } from "../pages/NotFoundPage.tsx";
import { RegisterPage } from "../pages/RegisterPage.tsx";
import { SettingsPage } from "../pages/SettingsPage.tsx";
import { ProtectedRoute } from "./ProtectedRoute";

function PublicOnly({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="center-shell" role="status" aria-live="polite">
        <div className="loading-card">Loading workspace...</div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route
        path="/login"
        element={
          <PublicOnly>
            <LoginPage />
          </PublicOnly>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnly>
            <RegisterPage />
          </PublicOnly>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
