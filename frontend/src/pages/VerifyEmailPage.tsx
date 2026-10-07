import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/auth";
import { extractErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

/** Opened from the emailed link. Works whether or not you're logged in on this device. */
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { me, refreshMe } = useAuth();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(
    token ? null : { ok: false, message: "This link is missing its code." },
  );
  const started = useRef(false);

  useEffect(() => {
    // Guard against StrictMode's double effect so the token is only submitted once.
    if (!token || started.current) return;
    started.current = true;
    verifyEmail(token)
      .then(async () => {
        setResult({ ok: true, message: "Your email is confirmed. You can place bets now." });
        await refreshMe();
      })
      .catch((err) =>
        setResult({ ok: false, message: extractErrorMessage(err, "That link didn't work.") }),
      );
  }, [token, refreshMe]);

  return (
    <div className="auth-card">
      <h1>{result === null ? "Confirming…" : result.ok ? "Email confirmed" : "Link problem"}</h1>
      {result && <p className="hint">{result.message}</p>}
      {result && (
        <p>
          {me ? <Link to="/">Go to games</Link> : <Link to="/login">Log in</Link>}
        </p>
      )}
    </div>
  );
}
