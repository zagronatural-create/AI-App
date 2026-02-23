# Production Blueprint: Supply Intelligence & Compliance Automation

## 1) Architecture Overview

### Services
- Traceability Engine Service
- Compliance Intelligence Service
- AI Risk Service
- Reporting & Audit Service

### Storage
- PostgreSQL for normalized operational records
- Object storage for lab PDFs and generated exports
- Redis for low-latency trace caching

### Key Principles
- AI-assisted validation and documentation intelligence
- No legal certification claims
- Explainable models over black-box systems

## 2) SQL Schema
Implemented in:
- `sql/001_init.sql`
- `sql/002_seed.sql`

Core tables include:
- Suppliers
- Raw Materials
- Supplier Deliveries
- Raw Material Lots
- Production Batches
- Finished Products
- Dispatch Records
- Quality Test Records
- Compliance Thresholds
- CCP Logs
- AI Risk Scores
- Recall Cases + Mapping
- Audit Logs
- KPI Daily

## 3) REST API Examples

### Traceability
- `GET /api/v1/trace/batch/{batch_code}/backward`
- `GET /api/v1/trace/batch/{batch_code}/forward`
- `GET /api/v1/trace/batch/{batch_code}/full`

### Authentication
- `GET /api/v1/auth/whoami`

### Audit
- `GET /api/v1/audit/events`
- `GET /api/v1/audit/events/export.csv`
- `GET /api/v1/audit/events/{audit_id}`
- `POST /api/v1/audit/packs/generate`
- `POST /api/v1/audit/packs/{pack_id}/verify`
- `GET /api/v1/audit/packs`
- `GET /api/v1/audit/packs/{pack_id}/download/{file_name}`

### Compliance
- `POST /api/v1/compliance/labs/reports/parse-text`
- `POST /api/v1/compliance/labs/reports/upload`
- `POST /api/v1/compliance/labs/reports/upload-async`
- `GET /api/v1/compliance/labs/reports/jobs/{job_id}`
- `GET /api/v1/compliance/labs/reports/{batch_code}/versions`
- `GET /api/v1/compliance/batch/{batch_code}/comparison`
- `GET /api/v1/compliance/batch/{batch_code}/export-readiness`

### AI Risk
- `POST /api/v1/ai/supplier/score`
- `GET /api/v1/ai/supplier/{supplier_id}/score`
- `POST /api/v1/ai/batch/{batch_code}/score`
- `POST /api/v1/ai/anomalies/run`
- `GET /api/v1/ai/anomalies`

### Recall
- `POST /api/v1/recall/simulate`

### CCP Monitoring
- `POST /api/v1/ccp/logs`
- `GET /api/v1/ccp/alerts`
- `PATCH /api/v1/ccp/alerts/{alert_id}/ack`
- `GET /api/v1/ccp/batch/{batch_code}/timeline`

### Internal UI
- `GET /ops`

### Dashboard
- `GET /api/v1/dashboard/overview`

### Automation
- `POST /api/v1/automation/run-daily`
- `POST /api/v1/automation/run-daily-async`
- `GET /api/v1/automation/runs`
- `GET /api/v1/automation/status`
- `POST /api/v1/automation/watchdog/mark-stuck-failed`

## 4) AI Model Logic

### Supplier Risk Score (0-100)
- Logistic baseline with feature contributions:
  - delay rate
  - quality fail rate
  - rejection rate
  - volume variability
  - critical nonconformities
- Response includes score, risk band, and explanation block.

### Batch Risk + Anomaly
- Batch risk is designed for next iteration using:
  - supplier risk score
  - raw material quality metrics
  - storage duration
  - historical deviations
- Anomaly detection planned with isolation forest + statistical thresholds.

## 5) Compliance Comparison Logic
- Batch test values are matched against threshold rows by:
  - parameter code
  - product category
  - active effective date
- For each standard (FSSAI/EU/Codex/HACCP internal), status rules:
  - FAIL: outside bounds
  - WARNING: near threshold (10% margin)
  - PASS: in-range and not near limit
- Roll-up status picks worst-case among standards.

## 6) Export Report Structure
`GET /api/v1/compliance/batch/{batch_code}/export-readiness`
returns:
- batch metadata
- compliance summary
- parameter-level comparison matrix
- readiness status: `PASS`, `CONDITIONAL_PASS`, `REVIEW_REQUIRED`
- disclaimer that output is assistive, not certification

## 7) Security & Integrity Controls (Implementation Plan)
- RBAC at API gateway and endpoint policy layer
- Immutable `audit_logs` with hash-chaining
- Lab report checksum and versioning
- PITR backups + restore drill schedule
- Retention policy by market/jurisdiction

## 8) 45-Day Build Roadmap
- Week 1-2: DB + trace engine
- Week 3-4: lab ingestion + mapping
- Week 5-6: AI scoring + anomaly
- Week 7: dashboard
- Week 8: testing + recall drills

## 9) KPIs
- Recall trace time p95 < 10 seconds
- Supplier risk visibility > 95%
- Compliance auto-validation %
- Audit export generation time
- Quality deviation trend reduction
