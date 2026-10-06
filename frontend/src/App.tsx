import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./Layout";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { GamesPage } from "./pages/GamesPage";
import { MyBetsPage } from "./pages/MyBetsPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { AccountPage } from "./pages/AccountPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<GamesPage />} />
          <Route path="/bets" element={<MyBetsPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
