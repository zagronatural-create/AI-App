# Mock Recall Drill

## Input
- Batch Code: `BATCH-2026-02-0012`

## Expected Output
- Backward trace: 2 suppliers, 2 raw material lots
- Forward trace: 1 finished lot, 2 customers
- Impacted dispatch quantity: 650 units
- Trace completion time target: < 10 seconds

## Procedure
1. Call `GET /api/v1/trace/batch/BATCH-2026-02-0012/full`.
2. Call `POST /api/v1/recall/simulate` with batch code.
3. Validate impacted nodes against dispatch records.
4. Log drill timestamp and response latency in KPI table.

## Compliance Note
This drill supports operational readiness and documentation; it does not replace statutory recall protocols.
