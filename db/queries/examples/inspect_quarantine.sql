-- Inspect the quarantine schema: source rows that failed to match a
-- player_id in the master. Counts by source and reason are the headline
-- view; sample rows reveal the actual naming issues to triage.
--
-- Run:
--   duckdb data/wc2026.duckdb -c "$(cat db/queries/examples/inspect_quarantine.sql)"

-- Per-source quarantine summary
SELECT 'sb_player_summary'              AS source, match_reason, COUNT(*) AS n
  FROM quarantine.unmatched_sb_player_summary           GROUP BY 2
UNION ALL
SELECT 'sb_player_stats_pedigree'       AS source, match_reason, COUNT(*) AS n
  FROM quarantine.unmatched_sb_player_stats_pedigree    GROUP BY 2
UNION ALL
SELECT 'understat_player_xg'            AS source, match_reason, COUNT(*) AS n
  FROM quarantine.unmatched_understat_player_xg         GROUP BY 2
UNION ALL
SELECT 'understat_2526_players'         AS source, match_reason, COUNT(*) AS n
  FROM quarantine.unmatched_understat_2526_players      GROUP BY 2
ORDER BY source, n DESC;
