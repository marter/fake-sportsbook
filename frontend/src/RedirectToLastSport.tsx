import { Navigate } from "react-router-dom";
import { getLastSport } from "./lastSport";

export function RedirectToLastSport() {
  return <Navigate to={`/games/${getLastSport()}`} replace />;
}
