# Regulatory Threshold Data Workflow

This workflow is for loading **real threshold values** (FSSAI, EU, Codex, HACCP internal) into the platform.

The system supports AI-assisted validation and documentation. It does **not** issue legal certification.

## 1) Prepare official source packet

For each release, collect:

- `standard_name`: `FSSAI`, `EU`, `CODEX`, or `HACCP_INTERNAL`
- `release_code`: unique code (example: `FSSAI-2025-11-MYCOTOXIN`)
- `document_title`: official circular/regulation title
- `document_url`: source URL (if available)
- `publication_date`: `YYYY-MM-DD`
- `effective_from`: `YYYY-MM-DD`
- `effective_to`: optional `YYYY-MM-DD`

## 2) Fill threshold CSV

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

## 3) Import release as draft

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

## 4) Approve and publish

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

## 5) Verify loaded data

```bash
curl -sS "https://ai-app-qgrl.onrender.com/api/v1/compliance/regulatory/releases?limit=20" \
  -H "Authorization: Bearer <VIEW_OR_ADMIN_TOKEN>"
```

```bash
curl -sS "https://ai-app-qgrl.onrender.com/api/v1/compliance/regulatory/releases/summary" \
  -H "Authorization: Bearer <VIEW_OR_ADMIN_TOKEN>"
```

Published releases are promoted into `compliance_thresholds` and become active for batch comparison by effective date.
