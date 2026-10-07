import { useState } from "react";
import { resendVerification } from "./api/auth";
import { extractErrorMessage } from "./api/client";
import { useAuth } from "./auth/AuthContext";

/** Shown until the user confirms their email; betting is blocked until then. */
export function VerifyBanner() {
  const { me } = useAuth();
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  if (!me || me.email_verified) return null;

  async function resend() {
    setError(null);
    setState("sending");
    try {
      await resendVerification();
      setState("sent");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't send the email."));
      setState("idle");
    }
  }

  return (
    <div className="verify-banner" role="status">
      <p>
        <strong>Confirm your email to start betting.</strong> We sent a link to {me.email}.
      </p>
      {state === "sent" ? (
        <p className="hint">Sent. Check your inbox (and spam folder).</p>
      ) : (
        <button type="button" className="btn-secondary" onClick={resend} disabled={state === "sending"}>
          {state === "sending" ? "Sending…" : "Resend email"}
        </button>
      )}
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}
