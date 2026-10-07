import { formatDateTime, formatMoney, formatSignedMoney } from "./format";
import type { LedgerEntry, LedgerKind } from "./types";

const KIND_LABEL: Record<LedgerKind, string> = {
  signup_bonus: "Starting balance",
  bet_stake: "Bet placed",
  bet_payout: "Bet won",
  bet_refund: "Bet refunded",
  admin_adjustment: "Adjusted by admin",
};

export function LedgerList({ entries }: { entries: LedgerEntry[] }) {
  return (
    <ul className="ledger-list">
      {entries.map((e) => (
        <li key={e.id}>
          <div>
            <p className="ledger-kind">{KIND_LABEL[e.kind]}</p>
            <p className="hint">
              {formatDateTime(e.created_at)}
              {e.note ? ` · ${e.note}` : ""}
            </p>
          </div>
          <div className="ledger-amounts">
            <p className={e.amount_cents >= 0 ? "amount-credit" : "amount-debit"}>
              {formatSignedMoney(e.amount_cents)}
            </p>
            <p className="hint">{formatMoney(e.balance_after_cents)}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
