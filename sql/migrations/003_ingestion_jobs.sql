CREATE TABLE IF NOT EXISTS ingestion_jobs (
  job_id UUID PRIMARY KEY,
  job_type TEXT NOT NULL DEFAULT 'LAB_REPORT_INGESTION',
  status TEXT NOT NULL,
  batch_code TEXT NOT NULL,
  payload JSONB NOT NULL,
  result JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs(status, created_at DESC);
