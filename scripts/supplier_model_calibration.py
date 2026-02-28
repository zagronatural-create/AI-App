#!/usr/bin/env python3
"""Calibration report for supplier risk scores using production delivery outcomes."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text


def _normalize_db_url(raw: str) -> str:
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--min-deliveries", type=int, default=3)
    parser.add_argument("--issue-threshold", type=float, default=0.10)
    parser.add_argument("--risk-threshold", type=float, default=0.66)
    parser.add_argument("--out-dir", default="storage/reports/model-calibration")
    args = parser.parse_args()

    if not args.database_url:
        raise RuntimeError("DATABASE_URL (or --database-url) is required")

    db_url = _normalize_db_url(args.database_url)
    engine = create_engine(db_url, pool_pre_ping=True)

    query = text(
        """
        WITH latest_scores AS (
          SELECT ars.entity_id AS supplier_id,
                 ars.score::float / 100.0 AS predicted_prob,
                 ars.scored_at,
                 ROW_NUMBER() OVER (PARTITION BY ars.entity_id ORDER BY ars.scored_at DESC) AS rn
          FROM ai_risk_scores ars
          WHERE ars.entity_type = 'supplier'
        ),
        delivery_outcomes AS (
          SELECT sd.supplier_id,
                 COUNT(*)::int AS deliveries_n,
                 SUM(CASE WHEN sd.status <> 'received' THEN 1 ELSE 0 END)::int AS issue_n
          FROM supplier_deliveries sd
          WHERE sd.received_at >= now() - (:lookback_days || ' day')::interval
          GROUP BY sd.supplier_id
        )
        SELECT
          ls.supplier_id::text AS supplier_id,
          ls.predicted_prob,
          COALESCE(d.deliveries_n, 0) AS deliveries_n,
          COALESCE(d.issue_n, 0) AS issue_n
        FROM latest_scores ls
        LEFT JOIN delivery_outcomes d ON d.supplier_id = ls.supplier_id
        WHERE ls.rn = 1
        ORDER BY ls.predicted_prob DESC
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(query, {"lookback_days": args.lookback_days}).mappings().all()

    eligible = []
    for r in rows:
        deliveries = int(r["deliveries_n"])
        issues = int(r["issue_n"])
        actual_rate = (issues / deliveries) if deliveries > 0 else None
        actual_flag = 1 if deliveries >= args.min_deliveries and actual_rate is not None and actual_rate >= args.issue_threshold else 0
        eligible.append(
            {
                "supplier_id": r["supplier_id"],
                "predicted_prob": float(r["predicted_prob"]),
                "deliveries_n": deliveries,
                "issue_n": issues,
                "actual_issue_rate": actual_rate,
                "actual_issue_flag": actual_flag,
                "eligible": deliveries >= args.min_deliveries,
            }
        )

    eval_rows = [r for r in eligible if r["eligible"]]
    sample_size = len(eval_rows)
    positives = sum(r["actual_issue_flag"] for r in eval_rows)
    avg_pred = _mean([r["predicted_prob"] for r in eval_rows]) if eval_rows else 0.0
    avg_actual = _mean([float(r["actual_issue_flag"]) for r in eval_rows]) if eval_rows else 0.0
    brier = _mean([(r["predicted_prob"] - float(r["actual_issue_flag"])) ** 2 for r in eval_rows]) if eval_rows else None

    predicted_positive = [r for r in eval_rows if r["predicted_prob"] >= args.risk_threshold]
    predicted_negative = [r for r in eval_rows if r["predicted_prob"] < args.risk_threshold]
    tp = sum(1 for r in predicted_positive if r["actual_issue_flag"] == 1)
    fp = sum(1 for r in predicted_positive if r["actual_issue_flag"] == 0)
    tn = sum(1 for r in predicted_negative if r["actual_issue_flag"] == 0)
    fn = sum(1 for r in predicted_negative if r["actual_issue_flag"] == 1)

    bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    calibration_bins = []
    ece = 0.0
    for lo, hi in bins:
        b_rows = [r for r in eval_rows if lo <= r["predicted_prob"] < hi]
        if not b_rows:
            continue
        pred_avg = _mean([r["predicted_prob"] for r in b_rows])
        actual_avg = _mean([float(r["actual_issue_flag"]) for r in b_rows])
        weight = len(b_rows) / sample_size if sample_size else 0.0
        ece += abs(pred_avg - actual_avg) * weight
        calibration_bins.append(
            {
                "bin": f"[{lo:.1f},{hi:.1f})",
                "n": len(b_rows),
                "avg_predicted_prob": round(pred_avg, 4),
                "actual_issue_rate": round(actual_avg, 4),
                "gap": round(pred_avg - actual_avg, 4),
            }
        )

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"supplier_calibration_{ts}.json"
    txt_path = out_dir / f"supplier_calibration_{ts}.txt"

    report = {
        "context": {
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "lookback_days": args.lookback_days,
            "min_deliveries": args.min_deliveries,
            "issue_threshold": args.issue_threshold,
            "risk_threshold": args.risk_threshold,
        },
        "summary": {
            "suppliers_with_scores": len(eligible),
            "suppliers_evaluated": sample_size,
            "positive_rate": round(avg_actual, 4),
            "avg_predicted_probability": round(avg_pred, 4),
            "brier_score": round(brier, 4) if brier is not None else None,
            "expected_calibration_error": round(ece, 4),
        },
        "confusion_matrix": {
            "threshold": args.risk_threshold,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        },
        "calibration_bins": calibration_bins,
        "disclaimer": "Calibration output supports model governance and does not provide regulatory certification.",
    }

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "Supplier Model Calibration Report",
        f"Generated (UTC): {report['context']['generated_at']}",
        f"Lookback days: {args.lookback_days}",
        f"Min deliveries for evaluation: {args.min_deliveries}",
        f"Issue threshold (actual label): {args.issue_threshold}",
        f"Risk threshold (predicted label): {args.risk_threshold}",
        "",
        f"Suppliers with latest scores: {report['summary']['suppliers_with_scores']}",
        f"Suppliers evaluated: {report['summary']['suppliers_evaluated']}",
        f"Positive rate: {report['summary']['positive_rate']}",
        f"Avg predicted probability: {report['summary']['avg_predicted_probability']}",
        f"Brier score: {report['summary']['brier_score']}",
        f"ECE: {report['summary']['expected_calibration_error']}",
        "",
        "Confusion matrix:",
        f"- TP={tp} FP={fp} TN={tn} FN={fn}",
        "",
        "Calibration bins:",
    ]
    for b in calibration_bins:
        lines.append(
            f"- {b['bin']}: n={b['n']}, avg_pred={b['avg_predicted_prob']}, "
            f"actual={b['actual_issue_rate']}, gap={b['gap']}"
        )
    lines.append("")
    lines.append(f"JSON: {json_path}")
    lines.append("Disclaimer: Model governance aid only; not legal certification.")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote report: {txt_path}")
    print(f"Wrote report: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
