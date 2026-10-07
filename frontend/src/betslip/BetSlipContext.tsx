import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Game, OddsLine, Selection } from "../types";

export const MAX_PICKS = 8;

interface BetSlipValue {
  picks: Selection[];
  isOpen: boolean;
  notice: string | null;
  /** Add a pick; tapping it again removes it; another line from the same game replaces it. */
  toggle: (game: Game, line: OddsLine) => void;
  remove: (lineId: string) => void;
  updateLine: (lineId: string, changes: Partial<OddsLine>) => void;
  clear: () => void;
  open: () => void;
  close: () => void;
}

const BetSlipContext = createContext<BetSlipValue | null>(null);

/** The bet slip lives above the pages so picks survive switching league tabs. */
export function BetSlipProvider({ children }: { children: ReactNode }) {
  const [picks, setPicks] = useState<Selection[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const toggle = useCallback(
    (game: Game, line: OddsLine) => {
      if (picks.some((p) => p.line.id === line.id)) {
        setPicks(picks.filter((p) => p.line.id !== line.id));
        setNotice(null);
        return;
      }
      const sameGame = picks.findIndex((p) => p.game.id === game.id);
      if (sameGame !== -1) {
        // One pick per game: swap in the new line.
        setPicks(picks.map((p, i) => (i === sameGame ? { game, line } : p)));
        setNotice("Replaced your other pick from this game (one pick per game).");
        return;
      }
      if (picks.length >= MAX_PICKS) {
        setNotice(`A parlay can have up to ${MAX_PICKS} picks.`);
        return;
      }
      setPicks([...picks, { game, line }]);
      setNotice(null);
    },
    [picks],
  );

  const remove = useCallback(
    (lineId: string) => {
      const next = picks.filter((p) => p.line.id !== lineId);
      setPicks(next);
      setNotice(null);
      if (next.length === 0) setIsOpen(false);
    },
    [picks],
  );

  const updateLine = useCallback((lineId: string, changes: Partial<OddsLine>) => {
    setPicks((current) =>
      current.map((p) => (p.line.id === lineId ? { ...p, line: { ...p.line, ...changes } } : p)),
    );
  }, []);

  const value = useMemo<BetSlipValue>(
    () => ({
      picks,
      isOpen,
      notice,
      toggle,
      remove,
      updateLine,
      clear: () => {
        setPicks([]);
        setNotice(null);
      },
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
    }),
    [picks, isOpen, notice, toggle, remove, updateLine],
  );

  return <BetSlipContext.Provider value={value}>{children}</BetSlipContext.Provider>;
}

export function useBetSlip(): BetSlipValue {
  const ctx = useContext(BetSlipContext);
  if (!ctx) throw new Error("useBetSlip must be used within BetSlipProvider");
  return ctx;
}
