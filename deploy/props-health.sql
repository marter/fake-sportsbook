-- Read-only health check for player props. On the server:
--   dc exec -T db psql -U sportsbook fake_sportsbook < deploy/props-health.sql

\echo '== Odds API credits: latest remaining, and API calls per kind since Oct 13 =='
SELECT requests_remaining, fetched_at, kind, sport_key
FROM odds_fetches
WHERE source = 'api' AND requests_remaining IS NOT NULL
ORDER BY fetched_at DESC LIMIT 1;

SELECT date_trunc('week', fetched_at)::date AS week, kind, count(*) AS api_calls,
       min(requests_remaining) AS min_remaining
FROM odds_fetches
WHERE source = 'api' AND fetched_at >= '2026-10-13'
GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== Props fetched per week (each NFL fetch costs 2 credits) =='
SELECT date_trunc('week', props_fetched_at)::date AS week, count(*) AS games
FROM games WHERE props_fetched_at IS NOT NULL
GROUP BY 1 ORDER BY 1;

\echo '== Prop legs by result =='
SELECT market, result::text, count(*)
FROM bet_legs WHERE participant <> ''
GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== Prop legs still pending on games that started over 12h ago (should be empty) =='
SELECT g.commence_time, g.away_team || ' @ ' || g.home_team AS game, g.completed,
       l.market, l.participant, l.outcome, l.point
FROM bet_legs l JOIN games g ON g.id = l.game_id
WHERE l.participant <> '' AND lower(l.result::text) = 'pending'
  AND g.commence_time < now() - interval '12 hours'
ORDER BY g.commence_time;

\echo '== Void rate per game (many voids on one game suggests name-matching misses) =='
SELECT g.commence_time::date, g.away_team || ' @ ' || g.home_team AS game,
       count(*) FILTER (WHERE lower(l.result::text) = 'void') AS voided, count(*) AS prop_legs
FROM bet_legs l JOIN games g ON g.id = l.game_id
WHERE l.participant <> ''
GROUP BY 1, 2 HAVING count(*) FILTER (WHERE lower(l.result::text) = 'void') > 0
ORDER BY 1;
