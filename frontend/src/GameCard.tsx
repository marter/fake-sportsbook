import { MarketHeaders } from "./MarketHelp";
import { useBetSlip } from "./betslip/BetSlipContext";
import type { Game, Market, OddsLine } from "./types";
import { formatAmericanOdds, formatKickoff, formatPoint, splitTeamName } from "./format";

function findLine(game: Game, market: Market, outcome: string): OddsLine | undefined {
  return game.odds_lines.find((l) => l.market === market && l.outcome === outcome);
}

interface CellProps {
  line: OddsLine | undefined;
  label?: string;
  isPicked: (line: OddsLine) => boolean;
  onSelect: (line: OddsLine) => void;
}

function OddsCell({ line, label, isPicked, onSelect }: CellProps) {
  if (!line) return <div className="odds-cell odds-cell--empty">–</div>;
  return (
    <button
      type="button"
      className="odds-cell"
      aria-pressed={isPicked(line)}
      onClick={() => onSelect(line)}
    >
      {label && <span className="odds-point">{label}</span>}
      <span className="odds-price">{formatAmericanOdds(line.price_american)}</span>
    </button>
  );
}

interface RowProps {
  game: Game;
  team: string;
  totalSide: "Over" | "Under";
  isPicked: (line: OddsLine) => boolean;
  onSelect: (line: OddsLine) => void;
}

function TeamRow({ game, team, totalSide, isPicked, onSelect }: RowProps) {
  const [city, nickname] = splitTeamName(team);
  const spread = findLine(game, "spreads", team);
  const total = findLine(game, "totals", totalSide);
  const cell = { isPicked, onSelect };

  return (
    <div className="game-row">
      <div className="team-name" title={team}>
        <span className="team-city">{city}</span>
        <span className="team-nickname">{nickname}</span>
      </div>
      <OddsCell
        line={spread}
        label={spread?.point != null ? formatPoint(spread.point) : undefined}
        {...cell}
      />
      <OddsCell
        line={total}
        label={total?.point != null ? `${totalSide[0]} ${total.point}` : undefined}
        {...cell}
      />
      <OddsCell line={findLine(game, "h2h", team)} {...cell} />
    </div>
  );
}

interface GameCardProps {
  game: Game;
  spreadLabel?: string;
}

export function GameCard({ game, spreadLabel }: GameCardProps) {
  const slip = useBetSlip();
  const select = (line: OddsLine) => slip.toggle(game, line);
  const isPicked = (line: OddsLine) => slip.picks.some((p) => p.line.id === line.id);
  return (
    <article className="game-card">
      <div className="game-row game-row--header">
        <span className="game-kickoff">{formatKickoff(game.commence_time)}</span>
        <MarketHeaders spreadLabel={spreadLabel} />
      </div>
      <TeamRow
        game={game}
        team={game.away_team}
        totalSide="Over"
        isPicked={isPicked}
        onSelect={select}
      />
      <TeamRow
        game={game}
        team={game.home_team}
        totalSide="Under"
        isPicked={isPicked}
        onSelect={select}
      />
    </article>
  );
}
