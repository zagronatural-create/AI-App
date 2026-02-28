# Regulatory Threshold Data Workflow

This workflow is for loading **real threshold values** (FSSAI, EU, Codex, HACCP internal) into the platform.

The system supports AI-assisted validation and documentation. It does **not** issue legal certification.

## 1) Use the authoritative bundle (recommended)

Curated bundle files are shipped in:

- `/Users/Raghunath/Documents/AI APP/data/regulatory/authoritative/authoritative_bundle.json`
- `/Users/Raghunath/Documents/AI APP/data/regulatory/authoritative/*.csv`
- `/Users/Raghunath/Documents/AI APP/data/regulatory/authoritative/SOURCES.md`

The bundle covers required parameters for `TRAD-NUTRI-500G` with normalized units and dated releases.

Before loading into production DB, apply:

- `/Users/Raghunath/Documents/AI APP/sql/migrations/011_regulatory_coverage_profile.sql`
- `/Users/Raghunath/Documents/AI APP/sql/migrations/012_regulatory_coverage_profile_v2.sql`

Run full load:

```bash
python3 /Users/Raghunath/Documents/AI\ APP/scripts/load_authoritative_regulatory_bundle.py \
  --base-url https://ai-app-qgrl.onrender.com \
  --token "<ADMIN_TOKEN>" \
  --approve \
  --publish \
  --skip-existing
```

This imports all FSSAI/EU/Codex/HACCP releases in the manifest, checks release coverage, then publishes.

## 2) Prepare official source packet (manual release path)

For each release, collect:

- `standard_name`: `FSSAI`, `EU`, `CODEX`, or `HACCP_INTERNAL`
- `release_code`: unique code (example: `FSSAI-2025-11-MYCOTOXIN`)
- `document_title`: official circular/regulation title
- `document_url`: source URL (if available)
- `publication_date`: `YYYY-MM-DD`
- `effective_from`: `YYYY-MM-DD`
- `effective_to`: optional `YYYY-MM-DD`
- `source_authority`: required (e.g., FSSAI, EFSA, Codex Secretariat, Internal HACCP Board)
- `source_clause`: required for every threshold row

## 3) Fill threshold CSV

Start from template:

- `/Users/Raghunath/Documents/AI APP/docs/templates/regulatory_threshold_template.csv`

Required columns:

- `product_category`
- `parameter_name`
- `unit`

Optional columns:

- `parameter_code`
- `limit_min`
- `limit_max`
- `severity` (`low|medium|high|critical`)
- `source_clause`
- `remarks`

Rules:

- At least one of `limit_min` or `limit_max` is required.
- One row per `(product_category, parameter_code)` per release.
- `source_clause` is required for each row.
- Units are normalized automatically; use canonical values where possible:
  - `%`
  - `ug/kg` (for ppb equivalents)
  - `mg/kg` (for ppm equivalents)
  - `cfu/g`
  - `cfu/25g`

## 4) Import release as draft

```bash
python3 /Users/Raghunath/Documents/AI\ APP/scripts/import_regulatory_release.py \
  --base-url https://ai-app-qgrl.onrender.com \
  --token "<ADMIN_OR_COMPLIANCE_TOKEN>" \
  --csv-file /absolute/path/fssai_release.csv \
  --standard-name FSSAI \
  --release-code FSSAI-2025-11-MYCOTOXIN \
  --document-title "FSSAI notification for mycotoxin limits" \
  --effective-from 2025-11-01 \
  --publication-date 2025-10-15 \
  --source-authority FSSAI
```

## 5) Approve and publish

```bash
python3 /Users/Raghunath/Documents/AI\ APP/scripts/import_regulatory_release.py \
  --base-url https://ai-app-qgrl.onrender.com \
  --token "<ADMIN_OR_COMPLIANCE_TOKEN>" \
  --csv-file /absolute/path/fssai_release.csv \
  --standard-name FSSAI \
  --release-code FSSAI-2025-11-MYCOTOXIN \
  --document-title "FSSAI notification for mycotoxin limits" \
  --effective-from 2025-11-01 \
  --publication-date 2025-10-15 \
  --source-authority FSSAI \
  --approve \
  --publish
```

## 6) Verify loaded data

```bash
curl -sS "https://ai-app-qgrl.onrender.com/api/v1/compliance/regulatory/releases?limit=20" \
  -H "Authorization: Bearer <VIEW_OR_ADMIN_TOKEN>"
```

```bash
curl -sS "https://ai-app-qgrl.onrender.com/api/v1/compliance/regulatory/releases/summary" \
  -H "Authorization: Bearer <VIEW_OR_ADMIN_TOKEN>"
```

Published releases are promoted into `compliance_thresholds` and become active for batch comparison by effective date.

## 7) Validate coverage completeness

Before final sign-off, run:

```bash
python3 /Users/Raghunath/Documents/AI\ APP/scripts/validate_regulatory_coverage.py \
  --base-url https://ai-app-qgrl.onrender.com \
  --token "<VIEW_OR_ADMIN_TOKEN>" \
  --product-category TRAD-NUTRI-500G
```

To validate a specific imported release:

```bash
python3 /Users/Raghunath/Documents/AI\ APP/scripts/validate_regulatory_coverage.py \
  --base-url https://ai-app-qgrl.onrender.com \
  --token "<VIEW_OR_ADMIN_TOKEN>" \
  --release-id "<release_uuid>"
```
