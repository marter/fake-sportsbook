import { formatAmericanOdds, formatDateTime, formatMoney, selectionLabel } from "./format";
import type { Bet } from "./types";

const STATUS_LABEL: Record<Bet["status"], string> = {
  pending: "Open",
  won: "Won",
  lost: "Lost",
  push: "Push",
  void: "Void",
};

export function BetCard({ bet }: { bet: Bet }) {
  const leg = bet.legs[0];
  const { game } = leg;
  const winnings = bet.potential_payout_cents - bet.stake_cents;

  return (
    <article className="bet-card">
      <div className="bet-card-top">
        <div>
          <p className="slip-label">{selectionLabel(leg.market, leg.outcome, leg.point)}</p>
          <p className="hint">
            {game.away_team} @ {game.home_team}
          </p>
        </div>
        <span className="slip-price">{formatAmericanOdds(leg.price_american)}</span>
      </div>
      <div className="bet-card-bottom">
        <span className="hint">
          {game.completed && game.away_score != null
            ? `Final: ${game.away_score}–${game.home_score}`
            : formatDateTime(game.commence_time)}
        </span>
        <span className={`status-badge status-badge--${bet.status}`}>
          {STATUS_LABEL[bet.status]}
        </span>
      </div>
      <dl className="bet-card-money">
        <div>
          <dt>Stake</dt>
          <dd>{formatMoney(bet.stake_cents)}</dd>
        </div>
        {bet.status === "pending" ? (
          <div>
            <dt>To win</dt>
            <dd>{formatMoney(winnings)}</dd>
          </div>
        ) : (
          <div>
            <dt>Paid out</dt>
            <dd>{formatMoney(bet.payout_cents ?? 0)}</dd>
          </div>
        )}
      </dl>
    </article>
  );
}
