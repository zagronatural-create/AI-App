CREATE TABLE IF NOT EXISTS anomaly_events (
  anomaly_id UUID PRIMARY KEY,
  source_ccp_log_id UUID REFERENCES ccp_logs(ccp_log_id),
  batch_id UUID REFERENCES production_batches(batch_id),
  anomaly_type TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  ccp_code TEXT NOT NULL,
  observed_value NUMERIC(14,6) NOT NULL,
  baseline_mean NUMERIC(14,6) NOT NULL,
  baseline_stddev NUMERIC(14,6) NOT NULL,
  z_score NUMERIC(14,6) NOT NULL,
  severity TEXT NOT NULL,
  details JSONB,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_ccp_log_id, anomaly_type)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_detected ON anomaly_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_batch ON anomaly_events(batch_id, detected_at DESC);
