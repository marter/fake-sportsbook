import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchUserBets } from "../api/admin";
import { extractErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BetCard } from "../BetCard";
import { BetTabs } from "../BetTabs";
import type { BetTab } from "../BetTabs";
import { formatMoney } from "../format";

/** Admin-only: another user's bets. */
export function UserBetsPage() {
  const { userId = "" } = useParams();
  const { me } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<BetTab>("open");
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-user-bets", userId, tab],
    queryFn: () => fetchUserBets(userId, tab),
    enabled: !!me?.is_admin,
  });

  if (!me?.is_admin) {
    return (
      <div className="empty-state">
        <p>Admins only.</p>
        <p className="hint">
          <Link to="/">Back to games</Link>
        </p>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        className="back-link"
        // React Router tracks history position in `idx`; 0 means this page was opened directly.
        onClick={() => (window.history.state?.idx > 0 ? navigate(-1) : navigate("/leaderboard"))}
      >
        ‹ Back
      </button>
      <h1>{data ? `${data.user.display_name}’s bets` : "Bets"}</h1>
      {data && (
        <p className="hint">
          {data.user.email} · balance {formatMoney(data.user.balance_cents)}
        </p>
      )}
      <BetTabs tab={tab} onChange={setTab} />
      {isLoading && <p className="page-loading">Loading…</p>}
      {error && <p className="form-error">{extractErrorMessage(error, "Couldn't load bets.")}</p>}
      {data && data.bets.length === 0 && (
        <div className="empty-state">
          <p>{tab === "open" ? "No open bets." : "No settled bets yet."}</p>
        </div>
      )}
      {data?.bets.map((bet) => <BetCard key={bet.id} bet={bet} />)}
    </>
  );
}
