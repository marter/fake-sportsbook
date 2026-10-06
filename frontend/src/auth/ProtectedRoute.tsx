import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { me, isLoading } = useAuth();

  if (isLoading) return <p className="page-loading">Loading…</p>;
  if (!me) return <Navigate to="/login" replace />;

  return <Outlet />;
}
