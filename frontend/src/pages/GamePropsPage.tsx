import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchGameProps } from "../api/games";
import { extractErrorMessage } from "../api/client";
import { useBetSlip } from "../betslip/BetSlipContext";
import { formatAmericanOdds, formatDateTime, splitTeamName } from "../format";
import type { Game, OddsLine, PropMarket } from "../types";

function PropButton({ game, line, label }: { game: Game; line: OddsLine; label?: string }) {
  const slip = useBetSlip();
  return (
    <button
      type="button"
      className="odds-cell prop-cell"
      aria-pressed={slip.picks.some((p) => p.line.id === line.id)}
      onClick={() => slip.toggle(game, line)}
    >
      {label && <span className="odds-point">{label}</span>}
      <span className="odds-price">{formatAmericanOdds(line.price_american)}</span>
    </button>
  );
}

function OverUnderMarket({ game, lines }: { game: Game; lines: OddsLine[] }) {
  const players = [...new Set(lines.map((l) => l.participant))].sort();
  return (
    <ul className="prop-rows">
      {players.map((player) => {
        const over = lines.find((l) => l.participant === player && l.outcome === "Over");
        const under = lines.find((l) => l.participant === player && l.outcome === "Under");
        return (
          <li key={player} className="prop-row">
            <span className="prop-player">
              {player}
              {over?.point != null && <span className="hint">Line {over.point}</span>}
            </span>
            {over ? <PropButton game={game} line={over} label="Over" /> : <span />}
            {under ? <PropButton game={game} line={under} label="Under" /> : <span />}
          </li>
        );
      })}
    </ul>
  );
}

function YesMarket({ game, lines }: { game: Game; lines: OddsLine[] }) {
  // Favorites first: the likeliest scorers lead the list, like a real book.
  const sorted = [...lines].sort((a, b) => {
    const prob = (p: number) => (p > 0 ? 100 / (p + 100) : -p / (-p + 100));
    return prob(b.price_american) - prob(a.price_american);
  });
  return (
    <ul className="prop-rows">
      {sorted.map((line) => (
        <li key={line.id} className="prop-row prop-row--yes">
          <span className="prop-player">{line.participant}</span>
          <PropButton game={game} line={line} label="Yes" />
        </li>
      ))}
    </ul>
  );
}

/** One game's player props. Picks go into the same bet slip as everything else. */
export function GamePropsPage() {
  const { gameId = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["props", gameId],
    queryFn: () => fetchGameProps(gameId),
    staleTime: 5 * 60_000,
  });

  const back = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate("/games"));
  const game = data?.game;

  return (
    <>
      <button type="button" className="back-link" onClick={back}>
        ‹ Games
      </button>
      {game ? (
        <div className="games-heading">
          <h1 className="props-title">
            {splitTeamName(game.away_team)[1]} @ {splitTeamName(game.home_team)[1]}
          </h1>
          <p className="hint">Player props · {formatDateTime(game.commence_time)}</p>
        </div>
      ) : (
        <h1>Player props</h1>
      )}
      {isLoading && <p className="page-loading">Loading props…</p>}
      {error && <p className="form-error">{extractErrorMessage(error, "Couldn't load props.")}</p>}
      {data?.unavailable_reason && (
        <div className="empty-state">
          <p>{data.unavailable_reason}</p>
          <p className="hint">
            <Link to="/games">Back to games</Link>
          </p>
        </div>
      )}
      {game &&
        !data?.unavailable_reason &&
        data?.markets.map((market: PropMarket) => {
          const lines = data.lines.filter((l) => l.market === market.key);
          if (lines.length === 0) return null;
          return (
            <section key={market.key} className="game-day">
              <h2>{market.label}</h2>
              <article className="game-card">
                {market.kind === "yes" ? (
                  <YesMarket game={game} lines={lines} />
                ) : (
                  <OverUnderMarket game={game} lines={lines} />
                )}
              </article>
            </section>
          );
        })}
      {game && !data?.unavailable_reason && (
        <p className="hint">
          A prop counts as your one pick for this game in a parlay. If a player doesn’t play, the
          bet is refunded.
        </p>
      )}
    </>
  );
}
