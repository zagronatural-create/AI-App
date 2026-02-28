-- Normalize requirement profile to the v2 authoritative coverage model.
-- This migration is safe to re-run.

UPDATE regulatory_parameter_requirements
SET effective_to = DATE '2026-01-31'
WHERE product_category = 'TRAD-NUTRI-500G'
  AND effective_to IS NULL
  AND effective_from < DATE '2026-02-01';

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
  ('TRAD-NUTRI-500G', 'AFLA_TOTAL', 'Aflatoxins Total', 'ug/kg', true, true, true, true, true, DATE '2026-02-01', 'Cross-standard mycotoxin core'),
  ('TRAD-NUTRI-500G', 'LEAD', 'Lead', 'mg/kg', true, true, true, true, true, DATE '2026-02-01', 'Cross-standard heavy metal core'),
  ('TRAD-NUTRI-500G', 'CADMIUM', 'Cadmium', 'mg/kg', true, true, true, true, true, DATE '2026-02-01', 'Cross-standard heavy metal core'),
  ('TRAD-NUTRI-500G', 'AFLA_B1', 'Aflatoxin B1', 'ug/kg', true, true, false, true, true, DATE '2026-02-01', 'FSSAI/EU legal limit + internal HACCP gate'),
  ('TRAD-NUTRI-500G', 'MOISTURE', 'Moisture', '%', false, false, false, true, true, DATE '2026-02-01', 'Internal CCP moisture gate'),
  ('TRAD-NUTRI-500G', 'SALMONELLA', 'Salmonella', 'cfu/25g', false, false, false, true, true, DATE '2026-02-01', 'Internal microbiological gate'),
  ('TRAD-NUTRI-500G', 'E_COLI', 'E. coli', 'cfu/g', false, false, false, true, true, DATE '2026-02-01', 'Internal microbiological gate'),
  ('TRAD-NUTRI-500G', 'YEAST_MOLD', 'Yeast and Mold', 'cfu/g', false, false, false, true, true, DATE '2026-02-01', 'Internal microbiological gate')
ON CONFLICT (product_category, parameter_code, effective_from) DO NOTHING;
