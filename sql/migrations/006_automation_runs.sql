CREATE TABLE IF NOT EXISTS automation_runs (
  run_id UUID PRIMARY KEY,
  run_type TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  actor_id TEXT NOT NULL,
  summary JSONB,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_automation_runs_started ON automation_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_runs_type_status ON automation_runs(run_type, status);
