import { useAuth } from "../auth/AuthContext";
import { formatMoney } from "../format";

export function AccountPage() {
  const { me, logout } = useAuth();
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
      <p className="hint">Play money only. Nothing here is real.</p>
      <button type="button" className="btn-secondary btn-block" onClick={logout}>
        Log out
      </button>
    </>
  );
}
