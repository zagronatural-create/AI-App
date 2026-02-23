CREATE TABLE IF NOT EXISTS ccp_rules (
  rule_id UUID PRIMARY KEY,
  ccp_code TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  limit_min NUMERIC(14,6),
  limit_max NUMERIC(14,6),
  warn_margin_pct NUMERIC(5,2) NOT NULL DEFAULT 10,
  severity TEXT NOT NULL DEFAULT 'high',
  active BOOLEAN NOT NULL DEFAULT true,
  source_ref TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (ccp_code, metric_name, unit, active)
);

CREATE TABLE IF NOT EXISTS alerts (
  alert_id UUID PRIMARY KEY,
  batch_id UUID REFERENCES production_batches(batch_id),
  ccp_log_id UUID REFERENCES ccp_logs(ccp_log_id),
  alert_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  details JSONB,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  acknowledged_at TIMESTAMPTZ,
  acknowledged_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_ccp_rules_lookup ON ccp_rules(ccp_code, metric_name, active);
CREATE INDEX IF NOT EXISTS idx_alerts_status_detected ON alerts(status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_batch ON alerts(batch_id, detected_at DESC);
