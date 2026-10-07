import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adjustBalance, deleteUnverifiedUser, fetchUsers, markVerified } from "../api/admin";
import type { Adjustment } from "../api/admin";
import { extractErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Modal } from "../Modal";
import { formatMoney, formatSignedMoney, parseDollars } from "../format";
import type { AdminUser } from "../types";

type Mode = "add" | "remove" | "set";

function VerificationActions({ user, onDone }: { user: AdminUser; onDone: () => void }) {
  const queryClient = useQueryClient();
  const done = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    queryClient.invalidateQueries({ queryKey: ["registration-open"] });
    onDone();
  };
  const verify = useMutation({ mutationFn: () => markVerified(user.id), onSuccess: done });
  const remove = useMutation({ mutationFn: () => deleteUnverifiedUser(user.id), onSuccess: done });
  const error = verify.error ?? remove.error;

  return (
    <div className="admin-verify">
      <p className="hint">
        {user.display_name} hasn’t confirmed their email, so they can’t bet. Unconfirmed accounts
        are deleted automatically after 48 hours.
      </p>
      <div className="slip-actions">
        <button
          type="button"
          className="btn-secondary btn-danger-text"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Delete ${user.email}? This frees their sign-up spot.`)) {
              remove.mutate();
            }
          }}
        >
          Delete account
        </button>
        <button type="button" disabled={verify.isPending} onClick={() => verify.mutate()}>
          Mark verified
        </button>
      </div>
      {error && <p className="form-error">{extractErrorMessage(error, "That didn't work.")}</p>}
    </div>
  );
}

function AdjustForm({ user, onDone }: { user: AdminUser; onDone: () => void }) {
  const { me, refreshMe } = useAuth();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("add");
  const [amountText, setAmountText] = useState("");
  const [note, setNote] = useState("");

  const amount = parseDollars(amountText);
  const delta =
    amount === null
      ? null
      : mode === "add"
        ? amount
        : mode === "remove"
          ? -amount
          : amount - user.balance_cents;
  const newBalance = delta === null ? null : user.balance_cents + delta;
  const problem =
    amount === null
      ? null
      : delta === 0
        ? "That doesn't change the balance"
        : newBalance! < 0
          ? "Balance can't go below $0"
          : null;

  const mutation = useMutation({
    mutationFn: (adjustment: Adjustment) => adjustBalance(user.id, adjustment),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      if (user.id === me?.id) {
        await refreshMe();
        queryClient.invalidateQueries({ queryKey: ["ledger"] });
      }
      onDone();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (amount === null || problem) return;
    const trimmed = note.trim() || undefined;
    mutation.mutate(
      mode === "set"
        ? { set_balance_cents: amount, note: trimmed }
        : { amount_cents: delta!, note: trimmed },
    );
  }

  return (
    <form className="admin-form" onSubmit={submit}>
      <p className="hint">
        {user.email} · current balance {formatMoney(user.balance_cents)}
      </p>
      <div className="segmented" role="radiogroup" aria-label="Adjustment type">
        {(
          [
            ["add", "Add"],
            ["remove", "Remove"],
            ["set", "Set to"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={mode === value}
            onClick={() => setMode(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="slip-stake">
        Amount
        <div className="money-input">
          <span aria-hidden="true">$</span>
          <input
            inputMode="decimal"
            autoComplete="off"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            required
          />
        </div>
      </label>
      <label className="slip-stake">
        Note (shown in their activity)
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
      </label>
      {delta !== null && !problem && (
        <p className="hint">
          {formatSignedMoney(delta)} → new balance {formatMoney(newBalance!)}
        </p>
      )}
      {problem && <p className="form-error">{problem}</p>}
      <Link to={`/admin/users/${user.id}/bets`} className="btn-link btn-secondary-link">
        View {user.display_name}’s bets
      </Link>
      {mutation.error && (
        <p className="form-error">{extractErrorMessage(mutation.error, "Couldn't adjust.")}</p>
      )}
      <button
        type="submit"
        className="btn-block"
        disabled={amount === null || !!problem || mutation.isPending}
      >
        {mutation.isPending ? "Saving…" : "Save adjustment"}
      </button>
    </form>
  );
}

export function AdminPage() {
  const { me } = useAuth();
  const { data: users, error } = useQuery({
    queryKey: ["admin-users"],
    queryFn: fetchUsers,
    enabled: !!me?.is_admin,
  });
  const [editing, setEditing] = useState<AdminUser | null>(null);

  if (!me?.is_admin) {
    return (
      <div className="empty-state">
        <p>Admins only.</p>
        <p className="hint">
          <Link to="/">Back to games</Link>
        </p>
      </div>
    );
  }

  return (
    <>
      <h1>Users</h1>
      {error && <p className="form-error">{extractErrorMessage(error, "Couldn't load users.")}</p>}
      <ul className="admin-users">
        {users?.map((u) => (
          <li key={u.id}>
            <button type="button" className="admin-user" onClick={() => setEditing(u)}>
              <span>
                <span className="ledger-kind">
                  {u.display_name}
                  {u.is_admin && <span className="status-badge status-badge--admin">Admin</span>}
                  {!u.email_verified && (
                    <span className="status-badge status-badge--admin status-badge--lost">
                      Unverified
                    </span>
                  )}
                </span>
                <span className="hint">{u.email}</span>
              </span>
              <span className="admin-balance">{formatMoney(u.balance_cents)}</span>
            </button>
          </li>
        ))}
      </ul>
      {editing && (
        <Modal title={`Adjust ${editing.display_name}`} onClose={() => setEditing(null)}>
          {!editing.email_verified && (
            <VerificationActions user={editing} onDone={() => setEditing(null)} />
          )}
          <AdjustForm user={editing} onDone={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}
