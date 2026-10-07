import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { useAuth } from "./auth/AuthContext";
import { OddsChangedError, placeBet } from "./api/bets";
import { extractErrorMessage } from "./api/client";
import {
  formatAmericanOdds,
  formatDateTime,
  formatMoney,
  parseDollars,
  payoutCents,
  selectionLabel,
} from "./format";
import type { Selection } from "./types";

const QUICK_STAKES = [500, 1_000, 2_500, 5_000];
const MIN_STAKE_CENTS = 100;

export function BetSlip({ selection, onClose }: { selection: Selection; onClose: () => void }) {
  const { me, refreshMe } = useAuth();
  const queryClient = useQueryClient();
  const [line, setLine] = useState(selection.line);
  const [stakeText, setStakeText] = useState("10");
  const [oddsChanged, setOddsChanged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlacing, setIsPlacing] = useState(false);
  const [placed, setPlaced] = useState(false);

  const { game } = selection;
  const balance = me?.balance_cents ?? 0;
  const stake = parseDollars(stakeText);
  const payout = stake ? payoutCents(stake, line.price_american) : 0;
  const stakeProblem =
    stake === null || stake < MIN_STAKE_CENTS
      ? `Minimum stake is ${formatMoney(MIN_STAKE_CENTS)}`
      : stake > balance
        ? "That's more than your balance"
        : null;

  async function submit() {
    if (stake === null || stakeProblem) return;
    setError(null);
    setIsPlacing(true);
    try {
      await placeBet(line, stake);
      setPlaced(true);
      await refreshMe();
      queryClient.invalidateQueries({ queryKey: ["bets"] });
      queryClient.invalidateQueries({ queryKey: ["ledger"] });
    } catch (err) {
      if (err instanceof OddsChangedError) {
        setLine({ ...line, price_american: err.price_american, point: err.point });
        setOddsChanged(true);
        queryClient.invalidateQueries({ queryKey: ["games"] });
      } else {
        setError(extractErrorMessage(err, "Couldn't place that bet."));
      }
    } finally {
      setIsPlacing(false);
    }
  }

  const label = selectionLabel(line.market, line.outcome, line.point);

  if (placed && stake !== null) {
    return (
      <Modal title="Bet placed" onClose={onClose}>
        <div className="slip-confirm">
          <p className="slip-confirm-check" aria-hidden="true">
            ✓
          </p>
          <p>
            <strong>{label}</strong> at {formatAmericanOdds(line.price_american)}
          </p>
          <p className="hint">
            {formatMoney(stake)} to win {formatMoney(payout - stake)}
          </p>
        </div>
        <div className="slip-actions">
          <Link to="/bets" className="btn-link btn-secondary-link" onClick={onClose}>
            View my bets
          </Link>
          <button type="button" onClick={onClose}>
            Done
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Bet slip" onClose={onClose}>
      <div className="slip-selection">
        <div>
          <p className="slip-label">{label}</p>
          <p className="hint">
            {game.away_team} @ {game.home_team} · {formatDateTime(game.commence_time)}
          </p>
        </div>
        <span className="slip-price">{formatAmericanOdds(line.price_american)}</span>
      </div>

      {oddsChanged && (
        <p className="slip-notice" role="status">
          The odds changed: now <strong>{label}</strong> at{" "}
          {formatAmericanOdds(line.price_american)}. Check the new payout before placing.
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
            aria-describedby="slip-stake-hint"
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

      <dl className="slip-summary" id="slip-stake-hint">
        <div>
          <dt>To win</dt>
          <dd>{stakeProblem ? "–" : formatMoney(payout - (stake ?? 0))}</dd>
        </div>
        <div>
          <dt>Total payout</dt>
          <dd>{stakeProblem ? "–" : formatMoney(payout)}</dd>
        </div>
        <div>
          <dt>Balance</dt>
          <dd>{formatMoney(balance)}</dd>
        </div>
      </dl>

      {stakeText !== "" && stakeProblem && <p className="form-error">{stakeProblem}</p>}
      {me && !me.email_verified && (
        <p className="slip-notice">Confirm your email first. Check your inbox for the link.</p>
      )}
      {error && <p className="form-error">{error}</p>}

      <button
        type="button"
        className="btn-block"
        disabled={!!stakeProblem || isPlacing || !me?.email_verified}
        onClick={submit}
      >
        {isPlacing
          ? "Placing…"
          : oddsChanged
            ? `Accept new odds and bet ${stake ? formatMoney(stake) : ""}`
            : `Place ${stake && !stakeProblem ? formatMoney(stake) : ""} bet`}
      </button>
    </Modal>
  );
}
