CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  country_code CHAR(2),
  fssai_license_no TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_materials (
  raw_material_id UUID PRIMARY KEY,
  material_name TEXT NOT NULL,
  category TEXT,
  unit TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS supplier_deliveries (
  delivery_id UUID PRIMARY KEY,
  supplier_id UUID NOT NULL REFERENCES suppliers(supplier_id),
  raw_material_id UUID NOT NULL REFERENCES raw_materials(raw_material_id),
  supplier_lot_code TEXT NOT NULL,
  received_qty NUMERIC(12,3) NOT NULL,
  received_at TIMESTAMPTZ NOT NULL,
  coa_doc_url TEXT,
  status TEXT NOT NULL DEFAULT 'received',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_material_lots (
  rm_lot_id UUID PRIMARY KEY,
  delivery_id UUID NOT NULL REFERENCES supplier_deliveries(delivery_id),
  internal_lot_code TEXT UNIQUE NOT NULL,
  qc_status TEXT NOT NULL DEFAULT 'pending',
  expiry_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_batches (
  batch_id UUID PRIMARY KEY,
  batch_code TEXT UNIQUE NOT NULL,
  product_sku TEXT NOT NULL,
  produced_at TIMESTAMPTZ NOT NULL,
  line_code TEXT,
  status TEXT NOT NULL DEFAULT 'released',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS batch_material_map (
  batch_id UUID NOT NULL REFERENCES production_batches(batch_id),
  rm_lot_id UUID NOT NULL REFERENCES raw_material_lots(rm_lot_id),
  qty_used NUMERIC(12,3) NOT NULL,
  PRIMARY KEY (batch_id, rm_lot_id)
);

CREATE TABLE IF NOT EXISTS finished_products (
  finished_id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES production_batches(batch_id),
  serial_lot_code TEXT UNIQUE NOT NULL,
  pack_size TEXT,
  mfg_date DATE NOT NULL,
  best_before DATE,
  qr_payload TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customers (
  customer_id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  customer_type TEXT NOT NULL,
  country_code CHAR(2),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dispatch_records (
  dispatch_id UUID PRIMARY KEY,
  finished_id UUID NOT NULL REFERENCES finished_products(finished_id),
  customer_id UUID NOT NULL REFERENCES customers(customer_id),
  dispatch_qty NUMERIC(12,3) NOT NULL,
  dispatched_at TIMESTAMPTZ NOT NULL,
  invoice_no TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lab_reports (
  report_id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES production_batches(batch_id),
  file_url TEXT NOT NULL,
  report_hash TEXT NOT NULL,
  lab_name TEXT,
  fssai_approved BOOLEAN,
  version_no INT NOT NULL DEFAULT 1,
  uploaded_by TEXT NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  supersedes_report_id UUID REFERENCES lab_reports(report_id)
);

CREATE TABLE IF NOT EXISTS quality_test_records (
  test_id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES production_batches(batch_id),
  report_id UUID NOT NULL REFERENCES lab_reports(report_id),
  parameter_code TEXT NOT NULL,
  parameter_name TEXT NOT NULL,
  observed_value NUMERIC(14,6) NOT NULL,
  unit TEXT NOT NULL,
  test_method TEXT,
  tested_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS compliance_thresholds (
  threshold_id UUID PRIMARY KEY,
  parameter_code TEXT NOT NULL,
  standard_name TEXT NOT NULL,
  product_category TEXT NOT NULL,
  limit_min NUMERIC(14,6),
  limit_max NUMERIC(14,6),
  unit TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'critical',
  effective_from DATE NOT NULL,
  effective_to DATE,
  source_ref TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS regulatory_threshold_releases (
  release_id UUID PRIMARY KEY,
  standard_name TEXT NOT NULL,
  release_code TEXT NOT NULL UNIQUE,
  jurisdiction TEXT,
  source_authority TEXT,
  document_title TEXT NOT NULL,
  document_url TEXT,
  publication_date DATE,
  effective_from DATE NOT NULL,
  effective_to DATE,
  review_status TEXT NOT NULL DEFAULT 'draft',
  imported_by TEXT NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  published_by TEXT,
  published_at TIMESTAMPTZ,
  notes TEXT,
  row_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (review_status IN ('draft', 'approved', 'published', 'rejected'))
);

CREATE TABLE IF NOT EXISTS regulatory_threshold_values (
  value_id UUID PRIMARY KEY,
  release_id UUID NOT NULL REFERENCES regulatory_threshold_releases(release_id) ON DELETE CASCADE,
  product_category TEXT NOT NULL,
  parameter_code TEXT NOT NULL,
  parameter_name TEXT NOT NULL,
  limit_min NUMERIC(14,6),
  limit_max NUMERIC(14,6),
  unit TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'critical',
  source_clause TEXT,
  remarks TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (limit_min IS NOT NULL OR limit_max IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS ccp_logs (
  ccp_log_id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES production_batches(batch_id),
  ccp_code TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value NUMERIC(14,6) NOT NULL,
  unit TEXT NOT NULL,
  measured_at TIMESTAMPTZ NOT NULL,
  operator_id TEXT,
  source TEXT NOT NULL DEFAULT 'iot',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS ai_risk_scores (
  risk_id UUID PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id UUID NOT NULL,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  score NUMERIC(5,2) NOT NULL,
  risk_band TEXT NOT NULL,
  explanation JSONB,
  scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recall_cases (
  recall_id UUID PRIMARY KEY,
  trigger_batch_id UUID NOT NULL REFERENCES production_batches(batch_id),
  initiated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'simulated',
  impacted_customers_count INT NOT NULL DEFAULT 0,
  impacted_qty NUMERIC(12,3) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recall_mapping (
  recall_mapping_id UUID PRIMARY KEY,
  recall_id UUID NOT NULL REFERENCES recall_cases(recall_id),
  batch_id UUID REFERENCES production_batches(batch_id),
  finished_id UUID REFERENCES finished_products(finished_id),
  customer_id UUID REFERENCES customers(customer_id),
  impact_type TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  audit_id UUID PRIMARY KEY,
  actor_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload JSONB,
  prev_hash TEXT,
  event_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_packs (
  pack_id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'generated',
  filters JSONB,
  row_count INT NOT NULL DEFAULT 0,
  folder_path TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  checksums_hash TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS kpi_daily (
  kpi_date DATE PRIMARY KEY,
  avg_recall_trace_time_ms NUMERIC(10,2),
  supplier_risk_coverage_pct NUMERIC(5,2),
  batch_compliance_auto_validation_pct NUMERIC(5,2),
  avg_audit_report_gen_time_sec NUMERIC(10,2),
  quality_deviation_rate NUMERIC(6,3)
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
  job_id UUID PRIMARY KEY,
  job_type TEXT NOT NULL DEFAULT 'LAB_REPORT_INGESTION',
  status TEXT NOT NULL, -- queued, processing, completed, failed
  batch_code TEXT NOT NULL,
  payload JSONB NOT NULL,
  result JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

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

CREATE INDEX IF NOT EXISTS idx_prod_batch_code ON production_batches(batch_code);
CREATE INDEX IF NOT EXISTS idx_dispatch_finished ON dispatch_records(finished_id);
CREATE INDEX IF NOT EXISTS idx_rm_delivery_supplier ON supplier_deliveries(supplier_id);
CREATE INDEX IF NOT EXISTS idx_qtr_batch ON quality_test_records(batch_id);
CREATE INDEX IF NOT EXISTS idx_threshold_lookup ON compliance_thresholds(parameter_code, standard_name, product_category);
CREATE INDEX IF NOT EXISTS idx_reg_release_standard ON regulatory_threshold_releases(standard_name, imported_at DESC);
CREATE INDEX IF NOT EXISTS idx_reg_release_status ON regulatory_threshold_releases(review_status, imported_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_value_release_key
ON regulatory_threshold_values(release_id, product_category, parameter_code);
CREATE INDEX IF NOT EXISTS idx_reg_value_lookup
ON regulatory_threshold_values(product_category, parameter_code);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs(status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_lab_report_version ON lab_reports(batch_id, lab_name, version_no);
CREATE INDEX IF NOT EXISTS idx_ccp_rules_lookup ON ccp_rules(ccp_code, metric_name, active);
CREATE INDEX IF NOT EXISTS idx_alerts_status_detected ON alerts(status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_batch ON alerts(batch_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_detected ON anomaly_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_batch ON anomaly_events(batch_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_runs_started ON automation_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_runs_type_status ON automation_runs(run_type, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_single_running_daily
ON automation_runs (run_type)
WHERE status = 'running' AND run_type = 'DAILY_CYCLE';
CREATE INDEX IF NOT EXISTS idx_audit_event_time ON audit_logs(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_logs(actor_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_logs(action_type, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity_lookup ON audit_logs(entity_type, entity_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_packs_created_at ON audit_packs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_packs_created_by ON audit_packs(created_by, created_at DESC);
