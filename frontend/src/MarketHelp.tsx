import { useEffect, useId, useRef, useState } from "react";
import type { Market } from "./types";

type MarketInfo = { market: Market; label: string; title: string; body: string };

const POINT_SPREAD: MarketInfo = {
  market: "spreads",
  label: "Spread",
  title: "Point spread",
  body:
    "Bet on the margin of victory. The favorite (−) has to win by more than the number; " +
    "the underdog (+) can lose by less than it, or win outright. −3.5 means win by 4 or more. " +
    "The number below is the price.",
};

const RUN_LINE: MarketInfo = {
  market: "spreads",
  label: "Run line",
  title: "Run line",
  body:
    "Baseball’s spread, almost always 1.5 runs. The favorite (−1.5) has to win by 2 or more; " +
    "the underdog (+1.5) can lose by 1 or win outright. The number below is the price.",
};

const OTHER_MARKETS: MarketInfo[] = [
  {
    market: "totals",
    label: "Total",
    title: "Total (over/under)",
    body:
      "Bet on the combined score of both teams. O 44.5 wins if they score 45 or more; " +
      "U 44.5 wins at 44 or fewer. The number below is the price.",
  },
  {
    market: "h2h",
    label: "Money",
    title: "Moneyline",
    body:
      "Bet on who wins the game, no points involved. −150 means you risk $150 to win $100; " +
      "+130 means you risk $100 to win $130.",
  },
];

/**
 * The Spread / Total / Money column headers. Tapping one shows what that bet means. These
 * are tap-to-toggle rather than hover tooltips, since hover doesn't exist on phones.
 */
export function MarketHeaders({ spreadLabel = "Spread" }: { spreadLabel?: string }) {
  const MARKETS = [spreadLabel === "Run line" ? RUN_LINE : POINT_SPREAD, ...OTHER_MARKETS];
  const [open, setOpen] = useState<Market | null>(null);
  const rowRef = useRef<HTMLDivElement>(null);
  const tipId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (!rowRef.current?.contains(e.target as Node)) setOpen(null);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(null);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const active = MARKETS.find((m) => m.market === open);

  return (
    <div className="market-headers" ref={rowRef}>
      {MARKETS.map(({ market, label }) => (
        <button
          key={market}
          type="button"
          className="market-header"
          aria-expanded={open === market}
          aria-describedby={open === market ? tipId : undefined}
          onClick={() => setOpen(open === market ? null : market)}
        >
          {label}
          <span className="market-header-icon" aria-hidden="true">
            ?
          </span>
        </button>
      ))}
      {active && (
        <div id={tipId} role="tooltip" className="market-tip">
          <strong>{active.title}</strong>
          <p>{active.body}</p>
        </div>
      )}
    </div>
  );
}
