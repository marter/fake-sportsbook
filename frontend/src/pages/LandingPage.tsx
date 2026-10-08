import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchRegistrationOpen } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import { getLastSport } from "../lastSport";

const FEATURES = [
  {
    image: "/landing/games.jpg",
    title: "Real games, real odds",
    body: "NFL, NBA and MLB lines from a real sportsbook, refreshed daily. Tap any price to pick it.",
  },
  {
    image: "/landing/slip.jpg",
    title: "Singles and parlays",
    body: "Bet one pick, or chain up to eight into a parlay for a bigger payout. Every pick has to hit.",
  },
  {
    image: "/landing/bets.jpg",
    title: "Results settle themselves",
    body: "Final scores come in automatically, and winnings land in your balance soon after the game ends.",
  },
  {
    image: "/landing/leaders.jpg",
    title: "Bragging rights",
    body: "A leaderboard ranks everyone by betting profit, so nobody can buy their way to the top.",
  },
];

/** The public front door. Logged-in users skip straight to their games. */
export function LandingPage() {
  const { me, isLoading } = useAuth();
  const { data: signupsOpen } = useQuery({
    queryKey: ["registration-open"],
    queryFn: fetchRegistrationOpen,
    enabled: !isLoading && !me,
  });

  if (isLoading) return <p className="page-loading">Loading…</p>;
  if (me) return <Navigate to={`/games/${getLastSport()}`} replace />;

  return (
    <div className="landing">
      <header className="landing-hero">
        <img src="/favicon.svg" alt="" width="56" height="56" />
        <h1>Fake Sportsbook</h1>
        <p className="landing-tagline">
          Bet on real NFL, NBA and MLB games with play money. Everyone starts with $1,000 and
          the leaderboard settles the arguments.
        </p>
        <p className="landing-disclaimer">No real money, ever. Nothing to deposit or withdraw.</p>
        <div className="landing-actions">
          <Link to="/login" className="landing-button landing-button--primary">
            Log in
          </Link>
          {signupsOpen !== false && (
            <Link to="/register" className="landing-button">
              Create account
            </Link>
          )}
        </div>
        {signupsOpen === false && (
          <p className="hint">Sign-ups are closed. It’s a small game among friends and it’s full.</p>
        )}
      </header>

      <section className="landing-features">
        {FEATURES.map((f) => (
          <article key={f.title} className="landing-feature">
            <img src={f.image} alt="" loading="lazy" width="600" height="1200" />
            <div>
              <h2>{f.title}</h2>
              <p>{f.body}</p>
            </div>
          </article>
        ))}
      </section>

      <footer className="landing-footer">
        <Link to="/login" className="landing-button landing-button--primary">
          Log in
        </Link>
        <p className="hint">
          A side project by <a href="https://martinteran.me">Martin Teran</a>.
        </p>
      </footer>
    </div>
  );
}
