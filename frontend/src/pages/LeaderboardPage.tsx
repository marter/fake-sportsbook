import { useEffect } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchLeaderboard } from "../api/leaderboard";
import { extractErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatSignedMoney } from "../format";
import type { LeaderboardRow } from "../types";

function record(row: LeaderboardRow): string {
  return row.pushes ? `${row.wins}–${row.losses}–${row.pushes}` : `${row.wins}–${row.losses}`;
}

function roi(row: LeaderboardRow): string | null {
  if (!row.staked_cents) return null;
  const pct = (row.profit_cents / row.staked_cents) * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(Math.abs(pct) < 10 ? 1 : 0)}% ROI`;
}

/** For admins the whole row links to that user's bets; for everyone else it's plain. */
function RowWrapper({
  linkTo,
  label,
  children,
}: {
  linkTo: string | null;
  label: string;
  children: ReactNode;
}) {
  if (!linkTo) return <div className="leaderboard-row">{children}</div>;
  return (
    <Link to={linkTo} className="leaderboard-row leaderboard-row--link" aria-label={label}>
      {children}
    </Link>
  );
}

export function LeaderboardPage() {
  const { me, refreshMe } = useAuth();
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["leaderboard"],
    queryFn: fetchLeaderboard,
  });

  // Loading the leaderboard can settle finished bets server-side.
  useEffect(() => {
    if (dataUpdatedAt) refreshMe();
  }, [dataUpdatedAt, refreshMe]);

  return (
    <>
      <h1>Leaderboard</h1>
      <p className="hint">
        Ranked by profit on settled bets. Starting money and admin adjustments don’t count.
        {me?.is_admin && " As an admin, tap anyone to see their bets."}
      </p>
      {isLoading && <p className="page-loading">Loading…</p>}
      {error && (
        <p className="form-error">{extractErrorMessage(error, "Couldn't load the leaderboard.")}</p>
      )}
      {data && (
        <ol className="leaderboard">
          {data.map((row) => {
            const settled = row.wins + row.losses + row.pushes;
            const isMe = row.user_id === me?.id;
            return (
              <li key={row.user_id} className={isMe ? "leaderboard-me" : undefined}>
                <RowWrapper
                  linkTo={me?.is_admin ? `/admin/users/${row.user_id}/bets` : null}
                  label={`See ${row.display_name}’s bets`}
                >
                  <span className={`leaderboard-rank leaderboard-rank--${row.rank}`}>
                    {row.rank}
                  </span>
                  <span className="leaderboard-name">
                    <span className="ledger-kind">
                      {row.display_name}
                      {isMe && <span className="status-badge status-badge--admin">You</span>}
                    </span>
                    <span className="hint">
                      {settled ? `${record(row)}` : "No settled bets"}
                      {roi(row) ? ` · ${roi(row)}` : ""}
                      {row.open_bets ? ` · ${row.open_bets} open` : ""}
                    </span>
                  </span>
                  <span
                    className={`leaderboard-profit ${
                      row.profit_cents > 0
                        ? "amount-credit"
                        : row.profit_cents < 0
                          ? "amount-loss"
                          : ""
                    }`}
                  >
                    {row.profit_cents ? formatSignedMoney(row.profit_cents) : "$0.00"}
                  </span>
                  {me?.is_admin && (
                    <span className="row-chevron" aria-hidden="true">
                      ›
                    </span>
                  )}
                </RowWrapper>
              </li>
            );
          })}
        </ol>
      )}
    </>
  );
}
