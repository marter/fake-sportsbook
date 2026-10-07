import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchBets } from "../api/bets";
import { extractErrorMessage } from "../api/client";
import { BetCard } from "../BetCard";
import { BetTabs } from "../BetTabs";
import type { BetTab } from "../BetTabs";
import { useAuth } from "../auth/AuthContext";

export function MyBetsPage() {
  const [tab, setTab] = useState<BetTab>("open");
  const { refreshMe } = useAuth();
  const { data: bets, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["bets", tab],
    queryFn: () => fetchBets(tab),
  });

  // Loading bets can settle finished games server-side, so refresh the header balance.
  useEffect(() => {
    if (dataUpdatedAt) refreshMe();
  }, [dataUpdatedAt, refreshMe]);

  return (
    <>
      <h1>My Bets</h1>
      <BetTabs tab={tab} onChange={setTab} />
      {isLoading && <p className="page-loading">Loading…</p>}
      {error && <p className="form-error">{extractErrorMessage(error, "Couldn't load bets.")}</p>}
      {bets && bets.length === 0 && (
        <div className="empty-state">
          {tab === "open" ? (
            <>
              <p>No open bets.</p>
              <p className="hint">
                Tap any odds on the <Link to="/">Games</Link> page to place one.
              </p>
            </>
          ) : (
            <>
              <p>No settled bets yet.</p>
              <p className="hint">Bets settle after the game ends.</p>
            </>
          )}
        </div>
      )}
      {bets?.map((bet) => <BetCard key={bet.id} bet={bet} />)}
    </>
  );
}
