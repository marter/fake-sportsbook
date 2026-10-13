import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchPropsToGrade, gradeLeg } from "./api/admin";
import { extractErrorMessage } from "./api/client";
import { formatAmericanOdds, formatDateTime, selectionLabel, splitTeamName } from "./format";

const RESULTS = [
  ["won", "Won"],
  ["lost", "Lost"],
  ["push", "Push"],
  ["void", "Void"],
] as const;

/** Player props automatic grading couldn't settle (ESPN didn't match the game or player). */
export function PropsToGrade() {
  const queryClient = useQueryClient();
  const { data: legs } = useQuery({ queryKey: ["props-to-grade"], queryFn: fetchPropsToGrade });
  const grade = useMutation({
    mutationFn: ({ legId, result }: { legId: string; result: (typeof RESULTS)[number][0] }) =>
      gradeLeg(legId, result),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["props-to-grade"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
        queryClient.invalidateQueries({ queryKey: ["leaderboard"] }),
      ]),
  });

  if (!legs || legs.length === 0) return null;

  return (
    <section className="attention">
      <h2>Props to grade</h2>
      <p className="hint">
        These player props couldn’t be graded automatically from ESPN’s box score. Check the
        player’s stats and grade each one. Void refunds it (e.g. the player didn’t play).
      </p>
      {legs.map((leg) => (
        <div key={leg.leg_id} className="attention-game">
          <p className="ledger-kind">
            {selectionLabel(leg)}{" "}
            <span className="hint">{formatAmericanOdds(leg.price_american)}</span>
          </p>
          <p className="hint">
            <Link to={`/admin/users/${leg.user_id}/bets`}>{leg.display_name}</Link> ·{" "}
            {splitTeamName(leg.away_team)[1]} {leg.away_score ?? "?"} @{" "}
            {splitTeamName(leg.home_team)[1]} {leg.home_score ?? "?"} ·{" "}
            {formatDateTime(leg.commence_time)}
          </p>
          <div className="grade-buttons">
            {RESULTS.map(([value, label]) => (
              <button
                key={value}
                type="button"
                className="btn-secondary"
                disabled={grade.isPending}
                onClick={() => grade.mutate({ legId: leg.leg_id, result: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {grade.error && (
        <p className="form-error">{extractErrorMessage(grade.error, "Couldn't grade that.")}</p>
      )}
    </section>
  );
}
