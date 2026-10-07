import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { fetchLedger } from "../api/bets";
import { formatMoney } from "../format";
import { LedgerList } from "../LedgerList";

export function AccountPage() {
  const { me, logout } = useAuth();
  const { data: ledger } = useQuery({ queryKey: ["ledger"], queryFn: () => fetchLedger(20) });
  if (!me) return null;

  return (
    <>
      <h1>Account</h1>
      <dl className="detail-list">
        <div>
          <dt>Name</dt>
          <dd>{me.display_name}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{me.email}</dd>
        </div>
        <div>
          <dt>Balance</dt>
          <dd>{formatMoney(me.balance_cents)}</dd>
        </div>
      </dl>
      {me.is_admin && (
        <Link to="/admin" className="btn-link btn-secondary-link">
          Admin: manage users
        </Link>
      )}
      <h2>Recent activity</h2>
      {ledger && <LedgerList entries={ledger} />}
      <p className="hint">Play money only. Nothing here is real.</p>
      <button type="button" className="btn-secondary btn-block" onClick={logout}>
        Log out
      </button>
    </>
  );
}
