# Operations Runbook

## Purpose
Operational setup for scheduler-safe daily automation cycle and watchdog recovery.

## Pre-checks
1. API is reachable at `API_BASE_URL`.
2. DB migrations applied through:
- `sql/migrations/003_ingestion_jobs.sql`
- `sql/migrations/004_ccp_alerts.sql`
- `sql/migrations/005_anomaly_events.sql`
- `sql/migrations/006_automation_runs.sql`
- `sql/migrations/007_automation_lock.sql`
3. `uvicorn` process (or service manager) is healthy.
4. Security config in `.env` reviewed:
- `AUTH_ENABLED=true`
- `CORS_ALLOW_ORIGINS` set to trusted domains
- `RATE_LIMIT_ENABLED=true` with production thresholds

## Endpoints
- Trigger daily cycle (async): `POST /api/v1/automation/run-daily-async`
- Watchdog stale-run cleanup: `POST /api/v1/automation/watchdog/mark-stuck-failed`
- Status: `GET /api/v1/automation/status`
- Run history: `GET /api/v1/automation/runs`
- Audit events: `GET /api/v1/audit/events`
- Audit export CSV: `GET /api/v1/audit/events/export.csv`
- Audit pack generation: `POST /api/v1/audit/packs/generate`
- Audit pack verification: `POST /api/v1/audit/packs/{pack_id}/verify`
- Audit pack download: `GET /api/v1/audit/packs/{pack_id}/download/{file_name}`

## Script usage
- Trigger: `scripts/run_daily_cycle.sh`
- Watchdog: `scripts/watchdog_automation.sh`
- Status check: `scripts/check_automation_status.sh`
- Post-go-live health check: `scripts/post_go_live_check.sh`

Set environment variables:
```bash
export API_BASE_URL="http://127.0.0.1:8000"
export ACTOR_ID="ops.scheduler"
export TIMEOUT_MINUTES="120"
export AUTH_TOKEN="ops-token"  # required when AUTH_ENABLED=true
```

## Cron examples
Use `crontab -e` on host where API is reachable.

```cron
# Run daily cycle every day at 01:05 local server time
5 1 * * * API_BASE_URL=http://127.0.0.1:8000 ACTOR_ID=ops.scheduler AUTH_TOKEN=ops-token /Users/Raghunath/Documents/AI\ APP/scripts/run_daily_cycle.sh >> /tmp/supply_intel_daily.log 2>&1

# Watchdog every 30 minutes
*/30 * * * * API_BASE_URL=http://127.0.0.1:8000 TIMEOUT_MINUTES=120 AUTH_TOKEN=ops-token /Users/Raghunath/Documents/AI\ APP/scripts/watchdog_automation.sh >> /tmp/supply_intel_watchdog.log 2>&1

# Optional status snapshot every morning
10 7 * * * API_BASE_URL=http://127.0.0.1:8000 AUTH_TOKEN=ops-token /Users/Raghunath/Documents/AI\ APP/scripts/check_automation_status.sh >> /tmp/supply_intel_status.log 2>&1
```

## Verification checklist
1. Trigger async run manually and confirm response contains `status=queued`.
2. Check `/api/v1/automation/status`:
- `daily_cycle_running` toggles true during execution.
3. Check `/api/v1/automation/runs?limit=5`:
- latest run appears with `status=completed` or actionable `failed` message.
4. Confirm `kpi_daily` updated for current date.
5. Confirm no duplicate `running` rows exist in `automation_runs`.

## Go-live acceptance command
```bash
python /Users/Raghunath/Documents/AI\ APP/scripts/go_live_acceptance.py \
  --base-url http://127.0.0.1:8000 \
  --admin-token dev-admin-token \
  --qa-token qa-token \
  --ops-token ops-token \
  --viewer-token viewer-token \
  --batch-code BATCH-2026-02-0012 \
  --out /Users/Raghunath/Documents/AI\ APP/storage/reports/go_live_acceptance.json
```

## Security regression command
```bash
python /Users/Raghunath/Documents/AI\ APP/scripts/security_regression.py \
  --base-url http://127.0.0.1:8000 \
  --admin-token dev-admin-token \
  --qa-token qa-token \
  --ops-token ops-token \
  --viewer-token viewer-token
```

## Release gate command
```bash
BASE_URL=http://127.0.0.1:8000 \
ADMIN_TOKEN=dev-admin-token \
QA_TOKEN=qa-token \
OPS_TOKEN=ops-token \
VIEWER_TOKEN=viewer-token \
BATCH_CODE=BATCH-2026-02-0012 \
/Users/Raghunath/Documents/AI\ APP/scripts/release_gate.sh
```
Outputs:
- `storage/reports/release_gate_<timestamp>.txt`
- `storage/reports/security_regression_<timestamp>.txt`
- `storage/reports/go_live_acceptance_<timestamp>.json`

## Post-go-live health check command
```bash
BASE_URL=https://<your-prod-api-domain> \
ADMIN_TOKEN=<admin-token> \
RUN_LIMIT=10 \
/Users/Raghunath/Documents/AI\ APP/scripts/post_go_live_check.sh
```
Outputs:
- `storage/reports/post-go-live/post_go_live_check_<timestamp>.txt`
- `storage/reports/post-go-live/post_go_live_check_<timestamp>.json`

## Staging release gate
1. Copy and update staging env template:
```bash
cp /Users/Raghunath/Documents/AI\ APP/staging.env.example /Users/Raghunath/Documents/AI\ APP/staging.env
```
2. Export secrets from `staging.env` (or secret manager).
3. Run:
```bash
BASE_URL=https://api-staging.example.com \
ADMIN_TOKEN=<staging-admin-token> \
QA_TOKEN=<staging-qa-token> \
OPS_TOKEN=<staging-ops-token> \
VIEWER_TOKEN=<staging-viewer-token> \
BATCH_CODE=BATCH-2026-02-0012 \
/Users/Raghunath/Documents/AI\ APP/scripts/run_staging_release_gate.sh
```
Outputs:
- `storage/reports/staging/release_gate_<timestamp>.txt`
- `storage/reports/staging/security_regression_<timestamp>.txt`
- `storage/reports/staging/go_live_acceptance_<timestamp>.json`

## Failure handling
- If run is stuck beyond SLA, call watchdog endpoint.
- If repeated failures occur:
1. Inspect `error_message` in `/api/v1/automation/runs`.
2. Check DB connectivity and table constraints.
3. Re-run manually with `POST /api/v1/automation/run-daily` for synchronous debugging.

## Compliance boundary
These automations provide AI-assisted risk and documentation operations. They do not issue legal food safety certifications.
