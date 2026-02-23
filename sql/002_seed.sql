INSERT INTO suppliers (supplier_id, name, country_code, status)
VALUES
('11111111-1111-1111-1111-111111111111', 'FarmCo Aggregators', 'IN', 'active'),
('22222222-2222-2222-2222-222222222222', 'DryNutri Mills', 'IN', 'active')
ON CONFLICT (supplier_id) DO NOTHING;

INSERT INTO raw_materials (raw_material_id, material_name, category, unit)
VALUES
('33333333-3333-3333-3333-333333333333', 'Millet', 'grain', 'kg'),
('44444444-4444-4444-4444-444444444444', 'Groundnut', 'nut', 'kg')
ON CONFLICT (raw_material_id) DO NOTHING;

INSERT INTO supplier_deliveries (delivery_id, supplier_id, raw_material_id, supplier_lot_code, received_qty, received_at)
VALUES
('55555555-5555-5555-5555-555555555555', '11111111-1111-1111-1111-111111111111', '33333333-3333-3333-3333-333333333333', 'FARM-MIL-782', 1200, now() - interval '12 days'),
('66666666-6666-6666-6666-666666666666', '22222222-2222-2222-2222-222222222222', '44444444-4444-4444-4444-444444444444', 'DN-GN-210', 800, now() - interval '10 days')
ON CONFLICT (delivery_id) DO NOTHING;

INSERT INTO raw_material_lots (rm_lot_id, delivery_id, internal_lot_code, qc_status)
VALUES
('77777777-7777-7777-7777-777777777777', '55555555-5555-5555-5555-555555555555', 'RM-LOT-8831', 'approved'),
('88888888-8888-8888-8888-888888888888', '66666666-6666-6666-6666-666666666666', 'RM-LOT-8832', 'approved')
ON CONFLICT (rm_lot_id) DO NOTHING;

INSERT INTO production_batches (batch_id, batch_code, product_sku, produced_at, line_code, status)
VALUES
('99999999-9999-9999-9999-999999999999', 'BATCH-2026-02-0012', 'TRAD-NUTRI-500G', now() - interval '8 days', 'L1', 'released')
ON CONFLICT (batch_id) DO NOTHING;

INSERT INTO batch_material_map (batch_id, rm_lot_id, qty_used)
VALUES
('99999999-9999-9999-9999-999999999999', '77777777-7777-7777-7777-777777777777', 380),
('99999999-9999-9999-9999-999999999999', '88888888-8888-8888-8888-888888888888', 220)
ON CONFLICT (batch_id, rm_lot_id) DO NOTHING;

INSERT INTO finished_products (finished_id, batch_id, serial_lot_code, pack_size, mfg_date, best_before, qr_payload)
VALUES
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '99999999-9999-9999-9999-999999999999', 'FG-LOT-1901', '500g', current_date - 8, current_date + 170, '{"batchCode":"BATCH-2026-02-0012"}')
ON CONFLICT (finished_id) DO NOTHING;

INSERT INTO customers (customer_id, name, customer_type, country_code)
VALUES
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'Distributor A', 'distributor', 'IN'),
('cccccccc-cccc-cccc-cccc-cccccccccccc', 'Exporter EU Node', 'exporter', 'DE')
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO dispatch_records (dispatch_id, finished_id, customer_id, dispatch_qty, dispatched_at, invoice_no)
VALUES
('dddddddd-dddd-dddd-dddd-dddddddddddd', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 400, now() - interval '6 days', 'INV-1021'),
('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 250, now() - interval '5 days', 'INV-1022')
ON CONFLICT (dispatch_id) DO NOTHING;

INSERT INTO lab_reports (report_id, batch_id, file_url, report_hash, lab_name, fssai_approved, version_no, uploaded_by)
VALUES
('f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0', '99999999-9999-9999-9999-999999999999', 's3://lab/reports/rep001.pdf', 'abc123hash', 'Trusted Labs', true, 1, 'qa.user')
ON CONFLICT (report_id) DO NOTHING;

INSERT INTO quality_test_records (test_id, batch_id, report_id, parameter_code, parameter_name, observed_value, unit, tested_at)
VALUES
('12121212-1212-1212-1212-121212121212', '99999999-9999-9999-9999-999999999999', 'f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0', 'MOISTURE', 'Moisture', 8.4, '%', now() - interval '7 days'),
('13131313-1313-1313-1313-131313131313', '99999999-9999-9999-9999-999999999999', 'f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0', 'AFLA_B1', 'Aflatoxin B1', 4.0, 'ppb', now() - interval '7 days')
ON CONFLICT (test_id) DO NOTHING;

INSERT INTO compliance_thresholds (threshold_id, parameter_code, standard_name, product_category, limit_max, unit, effective_from, source_ref)
VALUES
('14141414-1414-1414-1414-141414141414', 'MOISTURE', 'FSSAI', 'TRAD-NUTRI-500G', 10.0, '%', current_date - 365, 'fssai_ref_moisture'),
('15151515-1515-1515-1515-151515151515', 'MOISTURE', 'EU', 'TRAD-NUTRI-500G', 9.0, '%', current_date - 365, 'eu_ref_moisture'),
('16161616-1616-1616-1616-161616161616', 'MOISTURE', 'CODEX', 'TRAD-NUTRI-500G', 10.0, '%', current_date - 365, 'codex_ref_moisture'),
('17171717-1717-1717-1717-171717171717', 'MOISTURE', 'HACCP_INTERNAL', 'TRAD-NUTRI-500G', 8.5, '%', current_date - 365, 'haccp_ccp_dry01'),
('18181818-1818-1818-1818-181818181818', 'AFLA_B1', 'FSSAI', 'TRAD-NUTRI-500G', 5.0, 'ppb', current_date - 365, 'fssai_ref_afla'),
('19191919-1919-1919-1919-191919191919', 'AFLA_B1', 'EU', 'TRAD-NUTRI-500G', 2.0, 'ppb', current_date - 365, 'eu_ref_afla'),
('20202020-2020-2020-2020-202020202020', 'AFLA_B1', 'CODEX', 'TRAD-NUTRI-500G', 5.0, 'ppb', current_date - 365, 'codex_ref_afla'),
('21212121-2121-2121-2121-212121212121', 'AFLA_B1', 'HACCP_INTERNAL', 'TRAD-NUTRI-500G', 2.0, 'ppb', current_date - 365, 'haccp_afla')
ON CONFLICT (threshold_id) DO NOTHING;

INSERT INTO kpi_daily (kpi_date, avg_recall_trace_time_ms, supplier_risk_coverage_pct, batch_compliance_auto_validation_pct, avg_audit_report_gen_time_sec, quality_deviation_rate)
VALUES
(current_date - 2, 680, 94.2, 78.5, 520, 0.087),
(current_date - 1, 520, 97.5, 82.1, 410, 0.072),
(current_date, 430, 98.0, 86.7, 320, 0.061)
ON CONFLICT (kpi_date) DO NOTHING;

INSERT INTO ccp_rules (rule_id, ccp_code, metric_name, unit, limit_min, limit_max, warn_margin_pct, severity, active, source_ref)
VALUES
('30303030-3030-3030-3030-303030303030', 'DRYING', 'temperature', 'C', 55, 65, 10, 'high', true, 'haccp_ccp_dry_temp'),
('31313131-3131-3131-3131-313131313131', 'DRYING', 'moisture', '%', NULL, 8.5, 10, 'high', true, 'haccp_ccp_dry_moisture'),
('32323232-3232-3232-3232-323232323232', 'COOLING', 'time_minutes', 'min', NULL, 45, 10, 'medium', true, 'haccp_ccp_cooling_time')
ON CONFLICT (rule_id) DO NOTHING;
