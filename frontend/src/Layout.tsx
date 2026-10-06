import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { formatMoney } from "./format";

const TABS = [
  { to: "/", label: "Games", icon: "M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18M12 3a9 9 0 1 1 0 18a9 9 0 0 1 0-18" },
  { to: "/bets", label: "My Bets", icon: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6" },
  { to: "/leaderboard", label: "Leaders", icon: "M5 21V10M12 21V4M19 21v-7" },
  { to: "/account", label: "Account", icon: "M12 12a4 4 0 1 0 0-8a4 4 0 0 0 0 8M4 21a8 8 0 0 1 16 0" },
];

export function Layout() {
  const { me } = useAuth();

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="brand">Fake Sportsbook</span>
        {me && (
          <span className="balance-pill" aria-label="Balance">
            {formatMoney(me.balance_cents)}
          </span>
        )}
      </header>
      <main className="page">
        <Outlet />
      </main>
      <nav className="tabbar">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.to === "/"} className="tabbar-item">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d={tab.icon} />
            </svg>
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
