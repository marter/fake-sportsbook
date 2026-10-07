import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchGames } from "../api/games";
import { extractErrorMessage } from "../api/client";
import { GameCard } from "../GameCard";
import { BetSlip } from "../BetSlip";
import { useAuth } from "../auth/AuthContext";
import { formatDayHeading, formatTimeAgo } from "../format";
import type { Game, Selection } from "../types";

function groupByDay(games: Game[]): [string, Game[]][] {
  const groups = new Map<string, Game[]>();
  for (const game of games) {
    const day = formatDayHeading(game.commence_time);
    groups.set(day, [...(groups.get(day) ?? []), game]);
  }
  return [...groups.entries()];
}

export function GamesPage() {
  const { refreshMe } = useAuth();
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["games"],
    queryFn: fetchGames,
    staleTime: 5 * 60_000,
  });
  const [selection, setSelection] = useState<Selection | null>(null);

  // Loading games can settle finished bets server-side, so refresh the header balance.
  useEffect(() => {
    if (dataUpdatedAt) refreshMe();
  }, [dataUpdatedAt, refreshMe]);

  return (
    <>
      <h1>NFL</h1>
      {isLoading && <p className="page-loading">Loading games…</p>}
      {error && <p className="form-error">{extractErrorMessage(error, "Could not load games.")}</p>}
      {data && data.games.length === 0 && (
        <div className="empty-state">
          <p>No upcoming games.</p>
          <p className="hint">Check back closer to the weekend.</p>
        </div>
      )}
      {data &&
        groupByDay(data.games).map(([day, games]) => (
          <section key={day} className="game-day">
            <h2>{day}</h2>
            {games.map((game) => (
              <GameCard
                key={game.id}
                game={game}
                selectedLineId={selection?.line.id ?? null}
                onSelect={(g, line) => setSelection({ game: g, line })}
              />
            ))}
          </section>
        ))}
      {data?.odds_updated_at && (
        <p className="hint odds-footnote">
          Odds updated {formatTimeAgo(data.odds_updated_at)}. They refresh weekly.
        </p>
      )}
      {selection && (
        <BetSlip
          key={selection.line.id}
          selection={selection}
          onClose={() => setSelection(null)}
        />
      )}
    </>
  );
}
