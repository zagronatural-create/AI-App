# Production Cutover Checklist

Use this checklist to move from validated staging to production safely.

## 0) Security hygiene (mandatory)
- Revoke any Personal Access Tokens shared in chat or screenshots.
- Create fresh GitHub token(s) with least privilege.
- Rotate API tokens used for `ADMIN_TOKEN`, `QA_TOKEN`, `OPS_TOKEN`, `VIEWER_TOKEN`.

## 1) Set production environment values
Create/update your production env file (or secret manager values):

```bash
BASE_URL=https://<your-prod-api-domain>
DATABASE_URL=postgresql+psycopg://<user>:<password>@<prod-db-host>:5432/supply_intel
APP_ENV=prod
STORAGE_DIR=storage
AUTH_ENABLED=true
CORS_ALLOW_ORIGINS=https://<your-ops-domain>
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=300
RATE_LIMIT_WINDOW_SECONDS=60
API_TOKEN_MAP_JSON='{"<admin-token>":{"user_id":"admin.prod","roles":["admin"]},"<qa-token>":{"user_id":"qa.prod","roles":["qa_manager","qa_analyst"]},"<ops-token>":{"user_id":"ops.prod","roles":["ops_scheduler"]},"<viewer-token>":{"user_id":"auditor.prod","roles":["viewer"]}}'
```

## 2) Database readiness
Run schema and seed/migrations in production database:

```bash
psql "postgresql://<user>:<password>@<prod-db-host>:5432/supply_intel" -f sql/001_init.sql
psql "postgresql://<user>:<password>@<prod-db-host>:5432/supply_intel" -f sql/002_seed.sql
```

If you already have live data, apply only required migrations under `sql/migrations/` according to your migration policy.

## 3) Deploy application
- Deploy API service with production env values.
- Confirm service health:

```bash
curl -fsS https://<your-prod-api-domain>/health
```

Expected:
- HTTP 200
- `{"status":"ok"}`

## 4) Run release gate on production endpoint
From repo root:

```bash
BASE_URL=https://<your-prod-api-domain> \
ADMIN_TOKEN=<admin-token> \
QA_TOKEN=<qa-token> \
OPS_TOKEN=<ops-token> \
VIEWER_TOKEN=<viewer-token> \
BATCH_CODE=BATCH-2026-02-0012 \
./scripts/run_staging_release_gate.sh
```

Expected:
- `Security regression: PASS`
- `Go-live acceptance: PASS`
- `Release gate: PASS`

Artifacts:
- `storage/reports/staging/release_gate_<timestamp>.txt`
- `storage/reports/staging/security_regression_<timestamp>.txt`
- `storage/reports/staging/go_live_acceptance_<timestamp>.json`

## 5) Operational drills (must pass)
### 5.1 Recall simulation
```bash
curl -X POST "https://<your-prod-api-domain>/api/v1/recall/simulate" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"batch_code":"BATCH-2026-02-0012","reason":"prod cutover drill"}'
```

Acceptance:
- Response returns impacted suppliers/customers/qty.
- End-to-end trace resolution completes under 10s.

### 5.2 Audit pack workflow
```bash
PACK_ID=$(curl -s -X POST "https://<your-prod-api-domain>/api/v1/audit/packs/generate" \
  -H "Authorization: Bearer <qa-token>" \
  -H "Content-Type: application/json" \
  -d '{"from_ts":"2026-01-01T00:00:00Z","to_ts":"2026-12-31T23:59:59Z","limit":10000,"notes":"prod cutover drill"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["pack_id"])')

curl -X POST "https://<your-prod-api-domain>/api/v1/audit/packs/$PACK_ID/verify" \
  -H "Authorization: Bearer <viewer-token>"
```

Acceptance:
- Verify response returns `"valid": true`.
- No missing files or checksum mismatches.

## 6) Enable schedulers
Enable automation jobs from `docs/OPS_RUNBOOK.md`:
- Daily cycle trigger
- Watchdog stuck-run recovery
- Optional daily status snapshot

## 7) Production monitoring
First 24 hours:
- Check `/api/v1/automation/status` every 2-4 hours.
- Confirm `/api/v1/automation/runs` shows successful completions.
- Confirm no sustained 5xx spikes in API logs.
- Confirm KPI pipeline updates `/api/v1/kpi/daily`.

## 8) Go / no-go criteria
Go only if all are true:
- Release gate pass on production endpoint.
- Recall drill trace under 10s.
- Audit pack verify valid.
- Auth/RBAC enforced (`AUTH_ENABLED=true`).
- No critical error spikes post-cutover.

## 9) Rollback triggers
Rollback immediately if any occur:
- Release gate failure on production.
- Trace/recall operations unavailable or >10s sustained.
- Audit pack verification mismatch in production drills.
- Authentication or authorization bypass detected.

Rollback actions:
- Revert to previous stable release.
- Restore previous environment variables.
- Re-run health and security regression checks.

## 10) Sign-off log
Record before final declaration:
- Deployment timestamp (UTC): `2026-02-28T10:08:33Z` (final live deploy + gate verification window)
- Release commit SHA: `9902729`
- Release tag: `release-gate-pass-2026-02-23` (baseline tag), plus current `main` with prod checklist/signoff updates
- Release gate report path: `storage/reports/render-prod/release_gate_20260228T100833Z.txt`
- Security regression report path: `storage/reports/render-prod/security_regression_20260228T100833Z.txt`
- Go-live acceptance report path: `storage/reports/render-prod/go_live_acceptance_20260228T100833Z.json`
- Recall drill result:
  - Endpoint: `POST /api/v1/recall/simulate`
  - Batch: `BATCH-2026-02-0012`
  - Outcome: `impacted_customers_count=2`, `impacted_qty=650.0`, `suppliers_count=2`, `finished_lots_count=1`
  - Timestamp (UTC): `2026-02-28T10:10:52Z`
- Audit pack verify result:
  - Pack ID: `700e27f7-6284-4f3c-9088-ee11255eb39e`
  - Verify outcome: `valid=true`, `missing_files=[]`, `mismatches=[]`
  - Download check: `checksums.json` HTTP `200`
  - Timestamp (UTC): `2026-02-28T10:10:53Z`
- Re-validation timestamp (UTC): `2026-02-28T10:23:37Z` (post-token-rotation production gate run)
- Re-validation commit SHA on `main`: `377ba7b`
- Re-validation release gate report path: `storage/reports/render-prod/release_gate_20260228T102337Z.txt`
- Re-validation security regression report path: `storage/reports/render-prod/security_regression_20260228T102337Z.txt`
- Re-validation go-live acceptance report path: `storage/reports/render-prod/go_live_acceptance_20260228T102337Z.json`
- Re-validation recall drill result:
  - Endpoint: `POST /api/v1/recall/simulate`
  - Batch: `BATCH-2026-02-0012`
  - Outcome: `impacted_customers_count=2`, `impacted_qty=650.0`, `suppliers_count=2`, `finished_lots_count=1`, `HTTP 200`
  - Trace response time: `0.668536s` (target `< 10s` met)
  - Timestamp (UTC): `2026-02-28T10:25:20Z`
- Re-validation audit pack verify result:
  - Pack ID: `7abae6f0-aac7-49b9-8d41-3bbde5cd44b2`
  - Verify outcome: `valid=true`, `missing_files=[]`, `mismatches=[]`
  - Download check: `checksums.json` HTTP `200`
  - Timestamp (UTC): `2026-02-28T10:23:51Z`
- Approver names (Engineering, QA, Operations): `Pending manual sign-off entry`
