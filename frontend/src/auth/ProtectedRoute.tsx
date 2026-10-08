import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { me, isLoading } = useAuth();

  if (isLoading) return <p className="page-loading">Loading…</p>;
  // Logged-out visitors go to the landing page (which links to log in), not straight to a form.
  if (!me) return <Navigate to="/" replace />;

  return <Outlet />;
}
