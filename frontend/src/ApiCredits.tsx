import { useQuery } from "@tanstack/react-query";
import { fetchApiUsage } from "./api/admin";
import { formatDateTime } from "./format";
import type { ApiUsage } from "./types";

const KIND_LABELS: Record<string, string> = {
  odds: "Game odds",
  scores: "Scores",
  props: "Player props",
};

const STATUS: Record<ApiUsage["status"], { label: string; className: string }> = {
  ok: { label: "On track", className: "status-badge--pending" },
  warning: { label: "On pace to run out", className: "status-badge--warning" },
  paused: { label: "Paused: low on credits", className: "status-badge--lost" },
};

/** "2026-12-01" -> "Dec 1", without time-zone shifts. */
function shortDate(isoDay: string): string {
  const [y, m, d] = isoDay.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Every day of the current month, with its credits (0 for days with no calls, null for days
 * still to come). */
function monthDays(usage: ApiUsage): { day: string; credits: number | null }[] {
  const [y, m] = usage.resets_on.split("-").map(Number);
  const start = new Date(y, m - 2, 1);
  const daysInMonth = new Date(y, m - 1, 0).getDate();
  const spent = new Map(usage.by_day.map((d) => [d.day, d.credits]));
  const today = new Date();
  return Array.from({ length: daysInMonth }, (_, i) => {
    const date = new Date(start.getFullYear(), start.getMonth(), i + 1);
    const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
    return { day, credits: date > today ? null : (spent.get(day) ?? 0) };
  });
}

/** This month's Odds API credits: how many are left and whether we're on pace to run out. */
export function ApiCredits() {
  const { data: usage } = useQuery({ queryKey: ["admin-api-usage"], queryFn: fetchApiUsage });
  if (!usage) return null;

  const pct = (n: number) => `${Math.min((n / usage.monthly_credits) * 100, 100)}%`;
  const status = STATUS[usage.status];
  const days = monthDays(usage);
  const busiest = Math.max(1, ...days.map((d) => d.credits ?? 0));
  const kinds = Object.entries(usage.by_kind).sort((a, b) => b[1] - a[1]);

  return (
    <section className="credits">
      <div className="credits-header">
        <h2>Odds API credits</h2>
        <span className={`status-badge ${status.className}`}>{status.label}</span>
      </div>

      <p className="credits-headline">
        <strong>{usage.remaining}</strong> left of {usage.monthly_credits}
        <span className="hint"> · resets {shortDate(usage.resets_on)}</span>
      </p>

      <div
        className="credits-meter"
        role="meter"
        aria-label="Credits used this month"
        aria-valuemin={0}
        aria-valuemax={usage.monthly_credits}
        aria-valuenow={usage.used}
      >
        <div className="credits-meter-used" style={{ width: pct(usage.used) }} />
        {usage.projected > usage.used && (
          <div
            className="credits-meter-projected"
            style={{ left: pct(usage.used), width: `calc(${pct(usage.projected)} - ${pct(usage.used)})` }}
          />
        )}
      </div>
      <p className="hint">
        {usage.used} used this month, on pace for about {usage.projected} by{" "}
        {shortDate(usage.resets_on)}.
        {usage.last_month_used !== null && <> Last month: {usage.last_month_used}.</>} Score
        checks and props pause below {usage.floor}.
      </p>

      {kinds.length > 0 && (
        <table className="credits-kinds">
          <tbody>
            {kinds.map(([kind, credits]) => (
              <tr key={kind}>
                <th scope="row">{KIND_LABELS[kind] ?? kind}</th>
                <td>{credits}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="credits-days" aria-label="Credits used per day this month">
        {days.map((d) => (
          <div
            key={d.day}
            className="credits-day"
            title={d.credits === null ? shortDate(d.day) : `${shortDate(d.day)}: ${d.credits} credits`}
          >
            {d.credits !== null && d.credits > 0 && (
              <div className="credits-day-bar" style={{ height: `${(d.credits / busiest) * 100}%` }} />
            )}
          </div>
        ))}
      </div>
      <p className="hint">
        Bars: credits per day.{" "}
        {usage.last_call_at
          ? `Last API call ${formatDateTime(usage.last_call_at)}.`
          : "No API calls yet this month."}
      </p>
    </section>
  );
}
