import { combinedAmericanOdds, formatAmericanOdds, selectionLabel } from "../format";
import { BetSlip } from "../BetSlip";
import { useBetSlip } from "./BetSlipContext";

/** Sits above the tab bar whenever the slip has picks; tapping it opens the slip. */
export function SlipBar() {
  const slip = useBetSlip();
  const { picks } = slip;
  if (slip.isOpen) return <BetSlip />;
  if (picks.length === 0) return null;

  const prices = picks.map((p) => p.line.price_american);
  const first = picks[0].line;
  const summary =
    picks.length === 1
      ? `${selectionLabel(first.market, first.outcome, first.point)} · ${formatAmericanOdds(first.price_american)}`
      : `${picks.length}-pick parlay · ${formatAmericanOdds(combinedAmericanOdds(prices))}`;

  return (
    <div className="slip-bar" role="region" aria-label="Bet slip">
      {slip.notice && <p className="slip-bar-notice">{slip.notice}</p>}
      <div className="slip-bar-row">
        <span className="slip-bar-count">{picks.length}</span>
        <span className="slip-bar-summary">{summary}</span>
        <button type="button" onClick={slip.open}>
          View slip
        </button>
      </div>
    </div>
  );
}
