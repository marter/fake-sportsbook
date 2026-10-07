import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { extractErrorMessage } from "../api/client";
import { fetchRegistrationOpen } from "../api/auth";

export function RegisterPage() {
  const { me, register } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: registrationOpen } = useQuery({
    queryKey: ["registration-open"],
    queryFn: fetchRegistrationOpen,
  });

  if (me) return <Navigate to="/" replace />;

  if (registrationOpen === false) {
    return (
      <div className="auth-card">
        <h1>Sign-ups are closed</h1>
        <p className="hint">This sportsbook is limited to a few friends, and it’s full.</p>
        <p>
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await register({ email, password, display_name: displayName });
      navigate("/");
    } catch (err) {
      setError(extractErrorMessage(err, "Could not register."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>Create an account</h1>
      <p className="hint">
        You start with $1,000 in play money. We’ll email you a link to confirm your address
        before you can bet.
      </p>
      <form onSubmit={handleSubmit}>
        <label>
          Display name
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={50}
            required
          />
        </label>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create account"}
        </button>
      </form>
      <p>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </div>
  );
}
