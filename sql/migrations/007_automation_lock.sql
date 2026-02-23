CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_single_running_daily
ON automation_runs (run_type)
WHERE status = 'running' AND run_type = 'DAILY_CYCLE';
