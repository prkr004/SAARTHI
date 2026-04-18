import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { AdminDashboardPage } from "../pages/AdminDashboardPage";
import { AdminLoginPage } from "../pages/AdminLoginPage";
import { AdminUploadDocumentsPage } from "../pages/AdminUploadDocumentsPage";
import { AdminUserApprovalPage } from "../pages/AdminUserApprovalPage";
import { ChatPage } from "../pages/ChatPage.tsx";
import { DocumentGeneratorPage } from "../pages/DocumentGeneratorPage.tsx";
import { LoginPage } from "../pages/LoginPage.tsx";
import { NotFoundPage } from "../pages/NotFoundPage.tsx";
import { RegisterPage } from "../pages/RegisterPage.tsx";
import { SettingsPage } from "../pages/SettingsPage.tsx";
import { AdminRoute } from "./AdminRoute";
import { ProtectedRoute } from "./ProtectedRoute";

function PublicOnly({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="center-shell" role="status" aria-live="polite">
        <div className="loading-card">Loading workspace...</div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={user?.role === "admin" ? "/admin/dashboard" : "/"} replace />;
  }

  return <>{children}</>;
}

function AdminPublicOnly({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="center-shell" role="status" aria-live="polite">
        <div className="loading-card">Loading admin portal...</div>
      </div>
    );
  }

  if (isAuthenticated) {
    if (user?.role === "admin") {
      return <Navigate to="/admin/dashboard" replace />;
    }
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

export function AppRouter() {
  return (
    <Routes>
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<ChatPage />} />
        <Route path="/drafting" element={<DocumentGeneratorPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route element={<AdminRoute />}>
        <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
        <Route path="/admin/users" element={<AdminUserApprovalPage />} />
        <Route path="/admin/uploads" element={<AdminUploadDocumentsPage />} />
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
      <Route
        path="/admin/login"
        element={
          <AdminPublicOnly>
            <AdminLoginPage />
          </AdminPublicOnly>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
