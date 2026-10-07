import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./Layout";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { GamesPage } from "./pages/GamesPage";
import { MyBetsPage } from "./pages/MyBetsPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { AccountPage } from "./pages/AccountPage";
import { AdminPage } from "./pages/AdminPage";
import { UserBetsPage } from "./pages/UserBetsPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";
import { RedirectToLastSport } from "./RedirectToLastSport";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<RedirectToLastSport />} />
          <Route path="/games" element={<RedirectToLastSport />} />
          <Route path="/games/:sport" element={<GamesPage />} />
          <Route path="/bets" element={<MyBetsPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/users/:userId/bets" element={<UserBetsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
