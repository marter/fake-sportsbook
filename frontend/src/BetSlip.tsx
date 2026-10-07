import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { useAuth } from "./auth/AuthContext";
import { OddsChangedError, placeBet } from "./api/bets";
import { extractErrorMessage } from "./api/client";
import { useBetSlip } from "./betslip/BetSlipContext";
import {
  combinedAmericanOdds,
  formatAmericanOdds,
  formatDateTime,
  formatMoney,
  parlayPayoutCents,
  parseDollars,
  selectionLabel,
} from "./format";

const QUICK_STAKES = [500, 1_000, 2_500, 5_000];
const MIN_STAKE_CENTS = 100;

interface Placed {
  stake: number;
  payout: number;
  label: string;
  odds: number;
}

/** The bet slip sheet: one pick is a single bet, two or more is a parlay. */
export function BetSlip() {
  const { me, refreshMe } = useAuth();
  const queryClient = useQueryClient();
  const slip = useBetSlip();
  const [stakeText, setStakeText] = useState("10");
  const [oddsChanged, setOddsChanged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlacing, setIsPlacing] = useState(false);
  const [placed, setPlaced] = useState<Placed | null>(null);

  const close = () => {
    setPlaced(null);
    slip.close();
  };

  if (placed) {
    return (
      <Modal title="Bet placed" onClose={close}>
        <div className="slip-confirm">
          <p className="slip-confirm-check" aria-hidden="true">
            ✓
          </p>
          <p>
            <strong>{placed.label}</strong> at {formatAmericanOdds(placed.odds)}
          </p>
          <p className="hint">
            {formatMoney(placed.stake)} to win {formatMoney(placed.payout - placed.stake)}
          </p>
        </div>
        <div className="slip-actions">
          <Link to="/bets" className="btn-link btn-secondary-link" onClick={close}>
            View my bets
          </Link>
          <button type="button" onClick={close}>
            Done
          </button>
        </div>
      </Modal>
    );
  }

  const picks = slip.picks;
  const prices = picks.map((p) => p.line.price_american);
  const isParlay = picks.length > 1;
  const odds = isParlay ? combinedAmericanOdds(prices) : (prices[0] ?? 0);
  const balance = me?.balance_cents ?? 0;
  const stake = parseDollars(stakeText);
  const payout = stake ? parlayPayoutCents(stake, prices) : 0;
  const stakeProblem =
    stake === null || stake < MIN_STAKE_CENTS
      ? `Minimum stake is ${formatMoney(MIN_STAKE_CENTS)}`
      : stake > balance
        ? "That's more than your balance"
        : null;
  const title = isParlay ? `${picks.length}-pick parlay` : "Bet slip";
  const summaryLabel = isParlay
    ? `${picks.length}-pick parlay`
    : picks[0]
      ? selectionLabel(picks[0].line.market, picks[0].line.outcome, picks[0].line.point)
      : "";

  async function submit() {
    if (stake === null || stakeProblem || picks.length === 0) return;
    setError(null);
    setIsPlacing(true);
    try {
      await placeBet(
        picks.map((p) => p.line),
        stake,
      );
      setPlaced({ stake, payout, label: summaryLabel, odds });
      slip.clear();
      setOddsChanged(false);
      await refreshMe();
      queryClient.invalidateQueries({ queryKey: ["bets"] });
      queryClient.invalidateQueries({ queryKey: ["ledger"] });
    } catch (err) {
      if (err instanceof OddsChangedError) {
        for (const c of err.changes) {
          slip.updateLine(c.odds_line_id, { price_american: c.price_american, point: c.point });
        }
        setOddsChanged(true);
        queryClient.invalidateQueries({ queryKey: ["games"] });
      } else {
        setError(extractErrorMessage(err, "Couldn't place that bet."));
      }
    } finally {
      setIsPlacing(false);
    }
  }

  return (
    <Modal title={title} onClose={close}>
      <ul className="slip-picks">
        {picks.map(({ game, line }) => (
          <li key={line.id}>
            <div className="slip-pick-text">
              <p className="slip-label">{selectionLabel(line.market, line.outcome, line.point)}</p>
              <p className="hint">
                {game.away_team} @ {game.home_team} · {formatDateTime(game.commence_time)}
              </p>
            </div>
            <span className="slip-price">{formatAmericanOdds(line.price_american)}</span>
            <button
              type="button"
              className="slip-remove"
              aria-label={`Remove ${selectionLabel(line.market, line.outcome, line.point)}`}
              onClick={() => slip.remove(line.id)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      {isParlay ? (
        <p className="hint">
          Every pick has to win. If any loses, the parlay loses; a pushed pick drops out.
        </p>
      ) : (
        <p className="hint">Add more picks from other games to make it a parlay.</p>
      )}

      {oddsChanged && (
        <p className="slip-notice" role="status">
          Some odds changed since you picked them. Check the new prices before placing.
        </p>
      )}

      <label className="slip-stake">
        Stake
        <div className="money-input">
          <span aria-hidden="true">$</span>
          <input
            inputMode="decimal"
            autoComplete="off"
            value={stakeText}
            onChange={(e) => setStakeText(e.target.value)}
          />
        </div>
      </label>
      <div className="chip-row">
        {QUICK_STAKES.map((cents) => (
          <button
            key={cents}
            type="button"
            className="chip"
            onClick={() => setStakeText(String(cents / 100))}
          >
            {formatMoney(cents).replace(".00", "")}
          </button>
        ))}
        <button
          type="button"
          className="chip"
          disabled={balance < MIN_STAKE_CENTS}
          onClick={() => setStakeText((balance / 100).toFixed(2))}
        >
          Max
        </button>
      </div>

      <dl className="slip-summary">
        <div>
          <dt>Odds</dt>
          <dd>{picks.length ? formatAmericanOdds(odds) : "–"}</dd>
        </div>
        <div>
          <dt>To win</dt>
          <dd>{stakeProblem ? "–" : formatMoney(payout - (stake ?? 0))}</dd>
        </div>
        <div>
          <dt>Payout</dt>
          <dd>{stakeProblem ? "–" : formatMoney(payout)}</dd>
        </div>
      </dl>
      <p className="hint">Balance {formatMoney(balance)}</p>

      {stakeText !== "" && stakeProblem && <p className="form-error">{stakeProblem}</p>}
      {me && !me.email_verified && (
        <p className="slip-notice">Confirm your email first. Check your inbox for the link.</p>
      )}
      {error && <p className="form-error">{error}</p>}

      <button
        type="button"
        className="btn-block"
        disabled={!!stakeProblem || isPlacing || !me?.email_verified || picks.length === 0}
        onClick={submit}
      >
        {isPlacing
          ? "Placing…"
          : `${oddsChanged ? "Accept new odds and place" : "Place"} ${
              stake && !stakeProblem ? formatMoney(stake) : ""
            } ${isParlay ? "parlay" : "bet"}`}
      </button>
    </Modal>
  );
}
