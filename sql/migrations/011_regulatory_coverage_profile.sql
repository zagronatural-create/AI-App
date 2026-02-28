CREATE TABLE IF NOT EXISTS regulatory_parameter_requirements (
  requirement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_category TEXT NOT NULL,
  parameter_code TEXT NOT NULL,
  parameter_name TEXT NOT NULL,
  canonical_unit TEXT NOT NULL,
  require_fssai BOOLEAN NOT NULL DEFAULT true,
  require_eu BOOLEAN NOT NULL DEFAULT true,
  require_codex BOOLEAN NOT NULL DEFAULT true,
  require_haccp_internal BOOLEAN NOT NULL DEFAULT true,
  is_mandatory BOOLEAN NOT NULL DEFAULT true,
  effective_from DATE NOT NULL,
  effective_to DATE,
  source_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (product_category, parameter_code, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_reg_param_req_lookup
ON regulatory_parameter_requirements(product_category, parameter_code, effective_from, effective_to);

INSERT INTO regulatory_parameter_requirements (
  product_category,
  parameter_code,
  parameter_name,
  canonical_unit,
  require_fssai,
  require_eu,
  require_codex,
  require_haccp_internal,
  is_mandatory,
  effective_from,
  source_note
)
VALUES
  -- Cross-standard mandatory core (FSSAI + EU + Codex + HACCP internal).
  ('TRAD-NUTRI-500G', 'AFLA_TOTAL', 'Aflatoxins Total', 'ug/kg', true, true, true, true, true, DATE '2026-02-01', 'Cross-standard mycotoxin core'),
  ('TRAD-NUTRI-500G', 'LEAD', 'Lead', 'mg/kg', true, true, true, true, true, DATE '2026-02-01', 'Cross-standard heavy metal core'),
  ('TRAD-NUTRI-500G', 'CADMIUM', 'Cadmium', 'mg/kg', true, true, true, true, true, DATE '2026-02-01', 'Cross-standard heavy metal core'),

  -- Additional required controls where Codex does not publish a direct numeric limit for the mapped commodity.
  ('TRAD-NUTRI-500G', 'AFLA_B1', 'Aflatoxin B1', 'ug/kg', true, true, false, true, true, DATE '2026-02-01', 'FSSAI/EU legal limit + internal HACCP gate'),

  -- HACCP-only mandatory controls for process and microbiology.
  ('TRAD-NUTRI-500G', 'MOISTURE', 'Moisture', '%', false, false, false, true, true, DATE '2026-02-01', 'Internal CCP moisture gate'),
  ('TRAD-NUTRI-500G', 'SALMONELLA', 'Salmonella', 'cfu/25g', false, false, false, true, true, DATE '2026-02-01', 'Internal microbiological gate'),
  ('TRAD-NUTRI-500G', 'E_COLI', 'E. coli', 'cfu/g', false, false, false, true, true, DATE '2026-02-01', 'Internal microbiological gate'),
  ('TRAD-NUTRI-500G', 'YEAST_MOLD', 'Yeast and Mold', 'cfu/g', false, false, false, true, true, DATE '2026-02-01', 'Internal microbiological gate')
ON CONFLICT (product_category, parameter_code, effective_from) DO NOTHING;
