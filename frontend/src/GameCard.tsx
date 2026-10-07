import { MarketHeaders } from "./MarketHelp";
import type { Game, Market, OddsLine } from "./types";
import { formatAmericanOdds, formatKickoff, formatPoint, splitTeamName } from "./format";

function findLine(game: Game, market: Market, outcome: string): OddsLine | undefined {
  return game.odds_lines.find((l) => l.market === market && l.outcome === outcome);
}

interface CellProps {
  line: OddsLine | undefined;
  label?: string;
  selectedLineId: string | null;
  onSelect: (line: OddsLine) => void;
}

function OddsCell({ line, label, selectedLineId, onSelect }: CellProps) {
  if (!line) return <div className="odds-cell odds-cell--empty">–</div>;
  return (
    <button
      type="button"
      className="odds-cell"
      aria-pressed={line.id === selectedLineId}
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
  selectedLineId: string | null;
  onSelect: (line: OddsLine) => void;
}

function TeamRow({ game, team, totalSide, selectedLineId, onSelect }: RowProps) {
  const [city, nickname] = splitTeamName(team);
  const spread = findLine(game, "spreads", team);
  const total = findLine(game, "totals", totalSide);
  const cell = { selectedLineId, onSelect };

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
  selectedLineId: string | null;
  onSelect: (game: Game, line: OddsLine) => void;
}

export function GameCard({ game, spreadLabel, selectedLineId, onSelect }: GameCardProps) {
  const select = (line: OddsLine) => onSelect(game, line);
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
        selectedLineId={selectedLineId}
        onSelect={select}
      />
      <TeamRow
        game={game}
        team={game.home_team}
        totalSide="Under"
        selectedLineId={selectedLineId}
        onSelect={select}
      />
    </article>
  );
}
