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

CREATE INDEX IF NOT EXISTS idx_audit_packs_created_at ON audit_packs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_packs_created_by ON audit_packs(created_by, created_at DESC);
