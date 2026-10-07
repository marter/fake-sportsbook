export type BetTab = "open" | "settled";

export function BetTabs({ tab, onChange }: { tab: BetTab; onChange: (tab: BetTab) => void }) {
  return (
    <div className="segmented" role="tablist">
      {(["open", "settled"] as const).map((t) => (
        <button
          key={t}
          type="button"
          role="tab"
          aria-selected={tab === t}
          onClick={() => onChange(t)}
        >
          {t === "open" ? "Open" : "Settled"}
        </button>
      ))}
    </div>
  );
}
