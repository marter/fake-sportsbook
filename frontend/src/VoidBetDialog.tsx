import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { voidBet } from "./api/admin";
import { extractErrorMessage } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import { Modal } from "./Modal";
import { formatMoney, selectionLabel } from "./format";
import type { Bet } from "./types";

export function VoidBetDialog({
  bet,
  ownerName,
  onClose,
}: {
  bet: Bet;
  ownerName: string;
  onClose: () => void;
}) {
  const { refreshMe } = useAuth();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const leg = bet.legs[0];

  const mutation = useMutation({
    mutationFn: () => voidBet(bet.id, note.trim() || undefined),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-user-bets"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
        queryClient.invalidateQueries({ queryKey: ["bets"] }),
        queryClient.invalidateQueries({ queryKey: ["ledger"] }),
        refreshMe(),
      ]);
      onClose();
    },
  });

  return (
    <Modal title="Void bet" onClose={onClose}>
      <p>
        Cancel {ownerName}’s <strong>{selectionLabel(leg.market, leg.outcome, leg.point)}</strong>{" "}
        bet and refund the {formatMoney(bet.stake_cents)} stake? This can’t be undone.
      </p>
      <label className="slip-stake">
        Reason (shown in their activity)
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={200}
          placeholder="Voided by admin"
        />
      </label>
      {mutation.error && (
        <p className="form-error">{extractErrorMessage(mutation.error, "Couldn't void that bet.")}</p>
      )}
      <button
        type="button"
        className="btn-danger btn-block"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? "Voiding…" : `Void and refund ${formatMoney(bet.stake_cents)}`}
      </button>
    </Modal>
  );
}
