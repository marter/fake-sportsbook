import {
  combinedAmericanOdds,
  formatAmericanOdds,
  formatDateTime,
  formatMoney,
  selectionLabel,
  splitTeamName,
} from "./format";
import type { ReactNode } from "react";
import type { Bet, BetLeg } from "./types";

const STATUS_LABEL: Record<Bet["status"], string> = {
  pending: "Open",
  won: "Won",
  lost: "Lost",
  push: "Push",
  void: "Void",
};

const LEG_MARK: Record<BetLeg["result"], string> = { pending: "•", won: "✓", lost: "✗", push: "–" };

function legScore(leg: BetLeg): string {
  const { game } = leg;
  return game.completed && game.away_score != null
    ? `Final: ${splitTeamName(game.away_team)[1]} ${game.away_score}, ` +
        `${splitTeamName(game.home_team)[1]} ${game.home_score}`
    : formatDateTime(game.commence_time);
}

function ParlayCard({ bet, actions }: { bet: Bet; actions?: ReactNode }) {
  const winnings = bet.potential_payout_cents - bet.stake_cents;
  return (
    <article className="bet-card">
      <div className="bet-card-top">
        <p className="slip-label">{bet.legs.length}-pick parlay</p>
        <span className="slip-price">
          {formatAmericanOdds(combinedAmericanOdds(bet.legs.map((l) => l.price_american)))}
        </span>
      </div>
      <ul className="parlay-legs">
        {bet.legs.map((leg, i) => (
          <li key={i} className={`parlay-leg parlay-leg--${leg.result}`}>
            <span className="parlay-leg-mark" aria-label={leg.result}>
              {LEG_MARK[leg.result]}
            </span>
            <span className="parlay-leg-text">
              <span className="parlay-leg-pick">
                {selectionLabel(leg.market, leg.outcome, leg.point)}{" "}
                <span className="hint">{formatAmericanOdds(leg.price_american)}</span>
              </span>
              <span className="hint">
                <span className="sport-tag">{leg.game.sport.toUpperCase()}</span>
                {leg.game.away_team} @ {leg.game.home_team} · {legScore(leg)}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <div className="bet-card-bottom">
        <span className="hint">Every pick must win</span>
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
            <dt>{bet.status === "void" || bet.status === "push" ? "Refunded" : "Paid out"}</dt>
            <dd>{formatMoney(bet.payout_cents ?? 0)}</dd>
          </div>
        )}
      </dl>
      {actions}
    </article>
  );
}

export function BetCard({ bet, actions }: { bet: Bet; actions?: ReactNode }) {
  if (bet.legs.length > 1) return <ParlayCard bet={bet} actions={actions} />;
  const leg = bet.legs[0];
  const { game } = leg;
  const winnings = bet.potential_payout_cents - bet.stake_cents;

  return (
    <article className="bet-card">
      <div className="bet-card-top">
        <div>
          <p className="slip-label">{selectionLabel(leg.market, leg.outcome, leg.point)}</p>
          <p className="hint">
            <span className="sport-tag">{game.sport.toUpperCase()}</span>
            {game.away_team} @ {game.home_team}
          </p>
        </div>
        <span className="slip-price">{formatAmericanOdds(leg.price_american)}</span>
      </div>
      <div className="bet-card-bottom">
        <span className="hint">
          {game.completed && game.away_score != null
            ? `Final: ${splitTeamName(game.away_team)[1]} ${game.away_score}, ` +
              `${splitTeamName(game.home_team)[1]} ${game.home_score}`
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
            <dt>{bet.status === "void" || bet.status === "push" ? "Refunded" : "Paid out"}</dt>
            <dd>{formatMoney(bet.payout_cents ?? 0)}</dd>
          </div>
        )}
      </dl>
      {actions}
    </article>
  );
}
