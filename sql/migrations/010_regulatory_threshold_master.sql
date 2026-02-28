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

CREATE INDEX IF NOT EXISTS idx_reg_release_standard ON regulatory_threshold_releases(standard_name, imported_at DESC);
CREATE INDEX IF NOT EXISTS idx_reg_release_status ON regulatory_threshold_releases(review_status, imported_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_value_release_key
ON regulatory_threshold_values(release_id, product_category, parameter_code);
CREATE INDEX IF NOT EXISTS idx_reg_value_lookup
ON regulatory_threshold_values(product_category, parameter_code);
