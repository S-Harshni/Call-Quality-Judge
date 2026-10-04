-- Quality insights from the judge's verdicts on the 154 real voice-agent calls.
-- Tables: calls(call_id, voice_config, language, behavior, expected), verdicts(call_id, check_id, fail, turn, quote, evidence_ok),
--         labels(call_id, check_id, fail) = reference labels from the voice agent's own logs.

-- name: fail_rate_by_check
SELECT check_id, ROUND(AVG(fail), 3) AS judge_fail_rate,
       (SELECT ROUND(AVG(l.fail), 3) FROM labels l WHERE l.check_id = v.check_id) AS logged_fail_rate
FROM verdicts v GROUP BY check_id ORDER BY judge_fail_rate DESC;

-- name: fail_rate_by_voice_config
WITH per_call AS (SELECT call_id, SUM(fail) AS fails, AVG(fail) AS rate FROM verdicts GROUP BY call_id)
SELECT c.voice_config, ROUND(AVG(p.rate), 3) AS fail_rate, COUNT(*) AS calls,
       ROUND(AVG(CASE WHEN p.fails = 0 THEN 1.0 ELSE 0.0 END), 3) AS clean_call_share
FROM per_call p JOIN calls c USING (call_id)
GROUP BY c.voice_config ORDER BY clean_call_share DESC;

-- name: fail_rate_by_language
SELECT c.language, v.check_id, ROUND(AVG(v.fail), 3) AS fail_rate
FROM verdicts v JOIN calls c USING (call_id) GROUP BY c.language, v.check_id ORDER BY c.language, fail_rate DESC;

-- name: fail_rate_by_customer_behavior
SELECT c.behavior, ROUND(AVG(v.fail), 3) AS fail_rate, COUNT(DISTINCT c.call_id) AS calls
FROM verdicts v JOIN calls c USING (call_id) GROUP BY c.behavior ORDER BY fail_rate DESC;

-- name: judge_vs_logs
SELECT v.check_id,
       SUM(CASE WHEN v.fail = 1 AND l.fail = 1 THEN 1 ELSE 0 END) AS both_fail,
       SUM(CASE WHEN v.fail = 1 AND l.fail = 0 THEN 1 ELSE 0 END) AS judge_only,
       SUM(CASE WHEN v.fail = 0 AND l.fail = 1 THEN 1 ELSE 0 END) AS logs_only
FROM verdicts v JOIN labels l USING (call_id, check_id) GROUP BY v.check_id;
