import { useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchGames, fetchSports } from "../api/games";
import { extractErrorMessage } from "../api/client";
import { GameCard } from "../GameCard";
import { BetSlip } from "../BetSlip";
import { useAuth } from "../auth/AuthContext";
import { SportTabs } from "../SportTabs";
import { setLastSport } from "../lastSport";
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
  const { sport: slug = "nfl" } = useParams();
  const { refreshMe } = useAuth();
  const { data: sports } = useQuery({ queryKey: ["sports"], queryFn: fetchSports });
  const sport = sports?.find((s) => s.slug === slug);
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["games", slug],
    queryFn: () => fetchGames(slug),
    staleTime: 5 * 60_000,
    enabled: !sports || !!sport,
  });

  useEffect(() => {
    if (sport) setLastSport(sport.slug);
  }, [sport]);
  // Remember which league the slip was opened in, so switching tabs closes it.
  const [picked, setPicked] = useState<{ sport: string; selection: Selection } | null>(null);
  const selection = picked?.sport === slug ? picked.selection : null;
  const setSelection = (next: Selection | null) =>
    setPicked(next ? { sport: slug, selection: next } : null);

  // Loading games can settle finished bets server-side, so refresh the header balance.
  useEffect(() => {
    if (dataUpdatedAt) refreshMe();
  }, [dataUpdatedAt, refreshMe]);

  if (sports && !sport) return <Navigate to="/games/nfl" replace />;

  return (
    <>
      {sports && <SportTabs sports={sports} />}
      <h1>{sport?.name ?? slug.toUpperCase()}</h1>
      {isLoading && <p className="page-loading">Loading games…</p>}
      {error && <p className="form-error">{extractErrorMessage(error, "Could not load games.")}</p>}
      {data && data.games.length === 0 && (
        <div className="empty-state">
          {sport && !sport.in_season ? (
            <>
              <p>{sport.name} is in the off-season.</p>
              <p className="hint">{sport.season_note}</p>
            </>
          ) : (
            <>
              <p>No upcoming games with odds right now.</p>
              <p className="hint">Odds usually appear a few days before games.</p>
            </>
          )}
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
                spreadLabel={sport?.spread_label}
                selectedLineId={selection?.line.id ?? null}
                onSelect={(g, line) => setSelection({ game: g, line })}
              />
            ))}
          </section>
        ))}
      {data?.odds_updated_at && (
        <p className="hint odds-footnote">
          Odds updated {formatTimeAgo(data.odds_updated_at)}. They refresh daily.
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
