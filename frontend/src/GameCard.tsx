import type { Game, Market, OddsLine } from "./types";
import { formatAmericanOdds, formatKickoff, formatPoint, splitTeamName } from "./format";

function findLine(game: Game, market: Market, outcome: string): OddsLine | undefined {
  return game.odds_lines.find((l) => l.market === market && l.outcome === outcome);
}

function OddsCell({ line, label }: { line: OddsLine | undefined; label?: string }) {
  if (!line) return <div className="odds-cell odds-cell--empty">–</div>;
  return (
    <div className="odds-cell">
      {label && <span className="odds-point">{label}</span>}
      <span className="odds-price">{formatAmericanOdds(line.price_american)}</span>
    </div>
  );
}

function TeamRow({ game, team, totalSide }: { game: Game; team: string; totalSide: "Over" | "Under" }) {
  const [city, nickname] = splitTeamName(team);
  const spread = findLine(game, "spreads", team);
  const total = findLine(game, "totals", totalSide);

  return (
    <div className="game-row">
      <div className="team-name" title={team}>
        <span className="team-city">{city}</span>
        <span className="team-nickname">{nickname}</span>
      </div>
      <OddsCell line={spread} label={spread?.point != null ? formatPoint(spread.point) : undefined} />
      <OddsCell
        line={total}
        label={total?.point != null ? `${totalSide[0]} ${total.point}` : undefined}
      />
      <OddsCell line={findLine(game, "h2h", team)} />
    </div>
  );
}

export function GameCard({ game }: { game: Game }) {
  return (
    <article className="game-card">
      <div className="game-row game-row--header">
        <span className="game-kickoff">{formatKickoff(game.commence_time)}</span>
        <span>Spread</span>
        <span>Total</span>
        <span>Money</span>
      </div>
      <TeamRow game={game} team={game.away_team} totalSide="Over" />
      <TeamRow game={game} team={game.home_team} totalSide="Under" />
    </article>
  );
}
