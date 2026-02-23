# Supply Intelligence and Compliance Automation System (Starter)

AI-assisted traceability, compliance intelligence, risk detection, and audit automation platform for traditional food operations.

## Scope boundary
This system supports validation and documentation workflows. It **does not issue legal certifications** for FSSAI, HACCP, ISO, or EU compliance.

## Tech stack
- FastAPI
- PostgreSQL
- SQLAlchemy + Alembic-ready layout
- Pydantic

## Quick start
1. Create Python environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Set environment variables:
   ```bash
   cp .env.example .env
   ```
3. Start PostgreSQL (Docker):
   ```bash
   docker compose up -d db
   ```
4. Apply schema and seed data:
   ```bash
   psql "$DATABASE_URL" -f sql/001_init.sql
   psql "$DATABASE_URL" -f sql/002_seed.sql
   ```
5. Run API:
   ```bash
   uvicorn app.main:app --reload
   ```

## Core endpoints
- `GET /health`
- `GET /ops` (internal monitoring UI)
- `GET /api/v1/auth/whoami`
- `GET /api/v1/audit/events`
- `GET /api/v1/audit/events/export.csv`
- `GET /api/v1/audit/events/{audit_id}`
- `POST /api/v1/audit/packs/generate`
- `POST /api/v1/audit/packs/{pack_id}/verify`
- `GET /api/v1/audit/packs`
- `GET /api/v1/audit/packs/{pack_id}/download/{file_name}`
- `GET /api/v1/trace/batch/{batch_code}/backward`
- `GET /api/v1/trace/batch/{batch_code}/forward`
- `GET /api/v1/trace/batch/{batch_code}/full`
- `POST /api/v1/ccp/logs`
- `GET /api/v1/ccp/alerts`
- `PATCH /api/v1/ccp/alerts/{alert_id}/ack`
- `GET /api/v1/ccp/batch/{batch_code}/timeline`
- `GET /api/v1/dashboard/overview`
- `POST /api/v1/automation/run-daily`
- `POST /api/v1/automation/run-daily-async`
- `GET /api/v1/automation/runs`
- `GET /api/v1/automation/status`
- `POST /api/v1/automation/watchdog/mark-stuck-failed`
- `POST /api/v1/compliance/labs/reports/parse-text`
- `POST /api/v1/compliance/labs/reports/upload` (multipart PDF upload)
- `POST /api/v1/compliance/labs/reports/upload-async` (queued processing)
- `GET /api/v1/compliance/labs/reports/jobs/{job_id}` (job status)
- `GET /api/v1/compliance/labs/reports/{batch_code}/versions`
- `GET /api/v1/compliance/batch/{batch_code}/comparison`
- `GET /api/v1/compliance/batch/{batch_code}/export-readiness`
- `POST /api/v1/recall/simulate`
- `POST /api/v1/ai/supplier/score`
- `GET /api/v1/ai/supplier/{supplier_id}/score`
- `POST /api/v1/ai/batch/{batch_code}/score`
- `POST /api/v1/ai/anomalies/run`
- `GET /api/v1/ai/anomalies`
- `GET /api/v1/kpi/daily`

## Authentication and RBAC
- Set `AUTH_ENABLED=true` to enforce token auth.
- Send either:
  - `Authorization: Bearer <token>`
  - `X-API-Key: <token>`
- Token-to-role mapping comes from `API_TOKEN_MAP_JSON` in `.env`.
- Verify identity and role mapping:
```bash
curl http://127.0.0.1:8000/api/v1/auth/whoami \
  -H "Authorization: Bearer dev-admin-token"
```

## Security hardening settings
- `CORS_ALLOW_ORIGINS`: comma-separated allowlist for browser origins.
- `RATE_LIMIT_ENABLED`: enables in-memory API rate limiting.
- `RATE_LIMIT_REQUESTS`: max requests per path/client in time window.
- `RATE_LIMIT_WINDOW_SECONDS`: rolling time window for rate limit.
- Write operations on `/api/*` require auth by default when `AUTH_ENABLED=true`.
- All responses include `X-Request-ID`.
- Validation and server errors are sanitized (no stack traces in API response).

Security regression check:
```bash
python scripts/security_regression.py \
  --base-url http://127.0.0.1:8000 \
  --admin-token dev-admin-token \
  --qa-token qa-token \
  --ops-token ops-token \
  --viewer-token viewer-token
```

Audit query example:
```bash
curl "http://127.0.0.1:8000/api/v1/audit/events?limit=20&action_type=CCP_ALERT_CREATED" \
  -H "Authorization: Bearer viewer-token"
```

Audit CSV export example:
```bash
curl -L "http://127.0.0.1:8000/api/v1/audit/events/export.csv?from_ts=2026-02-01T00:00:00Z&to_ts=2026-02-28T23:59:59Z" \
  -H "Authorization: Bearer viewer-token" \
  -o audit_events_feb.csv
```

Audit pack generation:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/audit/packs/generate" \
  -H "Authorization: Bearer qa-token" \
  -H "Content-Type: application/json" \
  -d '{"from_ts":"2026-02-01T00:00:00Z","to_ts":"2026-02-28T23:59:59Z","limit":10000,"notes":"Monthly compliance submission"}'
```

Audit pack download:
```bash
curl -L "http://127.0.0.1:8000/api/v1/audit/packs/<pack_id>/download/audit_events.csv" \
  -H "Authorization: Bearer viewer-token" \
  -o audit_events_pack.csv
```

## QR helper
Generate QR image for batch payload:
```bash
python scripts/generate_qr.py --batch-code BATCH-2026-02-0012 --out batch.png
```

## Lab PDF upload example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/compliance/labs/reports/upload \
  -F "batch_code=BATCH-2026-02-0012" \
  -F "uploaded_by=qa.user" \
  -F "lab_name=Trusted Labs" \
  -F "fssai_approved=true" \
  -F "file=@/absolute/path/report.pdf"
```

## Async lab upload example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/compliance/labs/reports/upload-async \
  -F "batch_code=BATCH-2026-02-0012" \
  -F "uploaded_by=qa.user" \
  -F "lab_name=Trusted Labs" \
  -F "fssai_approved=true" \
  -F "file=@/absolute/path/report.pdf"
```

Then check:
```bash
curl http://127.0.0.1:8000/api/v1/compliance/labs/reports/jobs/<job_id>
```

## CCP log ingestion example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ccp/logs \
  -H 'Content-Type: application/json' \
  -d '{
    "batch_code":"BATCH-2026-02-0012",
    "ccp_code":"DRYING",
    "metric_name":"temperature",
    "metric_value":66.2,
    "unit":"C",
    "measured_at":"2026-02-23T09:30:00Z",
    "operator_id":"qa.operator",
    "source":"iot"
  }'
```

## Alert acknowledgment example
```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/ccp/alerts/<alert_id>/ack \
  -H 'Content-Type: application/json' \
  -d '{"acknowledged_by":"qa.manager"}'
```

## Batch risk scoring example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ai/batch/BATCH-2026-02-0012/score
```

## Anomaly scan run example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ai/anomalies/run \
  -H 'Content-Type: application/json' \
  -d '{"lookback_hours":72,"z_threshold":2.5,"actor_id":"qa.manager"}'
```

## Daily automation cycle
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/automation/run-daily?actor_id=ops.scheduler"
curl "http://127.0.0.1:8000/api/v1/automation/runs?limit=20"
```

## Scheduler-safe trigger
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/automation/run-daily-async?actor_id=ops.scheduler"
curl "http://127.0.0.1:8000/api/v1/automation/status"
curl -X POST "http://127.0.0.1:8000/api/v1/automation/watchdog/mark-stuck-failed?timeout_minutes=120"
```

Detailed cron and operations rollout:
- `docs/OPS_RUNBOOK.md`

## Go-live acceptance check
```bash
python scripts/go_live_acceptance.py \
  --base-url http://127.0.0.1:8000 \
  --admin-token dev-admin-token \
  --qa-token qa-token \
  --ops-token ops-token \
  --viewer-token viewer-token \
  --batch-code BATCH-2026-02-0012
```

## One-command release gate
```bash
BASE_URL=http://127.0.0.1:8000 \
ADMIN_TOKEN=dev-admin-token \
QA_TOKEN=qa-token \
OPS_TOKEN=ops-token \
VIEWER_TOKEN=viewer-token \
BATCH_CODE=BATCH-2026-02-0012 \
./scripts/release_gate.sh
```

## Staging release gate
```bash
BASE_URL=https://api-staging.example.com \
ADMIN_TOKEN=<staging-admin-token> \
QA_TOKEN=<staging-qa-token> \
OPS_TOKEN=<staging-ops-token> \
VIEWER_TOKEN=<staging-viewer-token> \
BATCH_CODE=BATCH-2026-02-0012 \
./scripts/run_staging_release_gate.sh
```
Staging config template:
- `staging.env.example`

## Internal dashboard
Open:
- `http://127.0.0.1:8000/ops`
