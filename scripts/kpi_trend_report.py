#!/usr/bin/env python3
"""Generate 24h/7d KPI trend report from the API."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_rows(base_url: str, token: str) -> list[dict]:
    req = Request(
        f"{base_url.rstrip('/')}/api/v1/kpi/daily",
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"KPI API failed with status {exc.code}: {body[:500]}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("KPI API returned non-JSON response") from exc

    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise RuntimeError("KPI API response missing rows[]")
    return [r for r in rows if isinstance(r, dict)]


def _find_date_row(rows: list[dict], target_date: datetime) -> dict | None:
    target = target_date.date().isoformat()
    by_date = {str(r.get("kpi_date")): r for r in rows}
    if target in by_date:
        return by_date[target]
    # fallback: nearest earlier row
    candidates = sorted([d for d in by_date if d <= target], reverse=True)
    if candidates:
        return by_date[candidates[0]]
    return None


def _delta_label(delta: float | None, higher_is_better: bool) -> str:
    if delta is None:
        return "unknown"
    if delta == 0:
        return "flat"
    improved = delta > 0 if higher_is_better else delta < 0
    return "improved" if improved else "worsened"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-token", required=True)
    parser.add_argument("--out-dir", default="storage/reports/kpi-trends")
    args = parser.parse_args()

    rows = _request_rows(args.base_url, args.admin_token)
    if not rows:
        raise RuntimeError("No KPI rows returned; cannot build trend report")

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"kpi_trend_{ts}.json"
    txt_path = out_dir / f"kpi_trend_{ts}.txt"

    # API already returns descending kpi_date; normalize just in case
    rows_sorted = sorted(rows, key=lambda r: str(r.get("kpi_date")), reverse=True)
    current = rows_sorted[0]
    previous_1d = rows_sorted[1] if len(rows_sorted) > 1 else None
    previous_7d = _find_date_row(rows_sorted, now - timedelta(days=7))

    metrics = [
        ("avg_recall_trace_time_ms", False, "ms", "<10000 target"),
        ("supplier_risk_coverage_pct", True, "%", "higher better"),
        ("batch_compliance_auto_validation_pct", True, "%", "higher better"),
        ("avg_audit_report_gen_time_sec", False, "sec", "lower better"),
        ("quality_deviation_rate", False, "ratio", "lower better"),
    ]

    metric_rows: list[dict] = []
    for key, higher_is_better, unit, note in metrics:
        cur = _to_float(current.get(key))
        prev_1d = _to_float(previous_1d.get(key)) if previous_1d else None
        prev_7d = _to_float(previous_7d.get(key)) if previous_7d else None
        d1 = (cur - prev_1d) if cur is not None and prev_1d is not None else None
        d7 = (cur - prev_7d) if cur is not None and prev_7d is not None else None
        metric_rows.append(
            {
                "metric": key,
                "unit": unit,
                "current": cur,
                "delta_24h": d1,
                "delta_7d": d7,
                "trend_24h": _delta_label(d1, higher_is_better),
                "trend_7d": _delta_label(d7, higher_is_better),
                "note": note,
            }
        )

    report = {
        "context": {
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "base_url": args.base_url,
            "current_kpi_date": current.get("kpi_date"),
            "reference_1d_kpi_date": previous_1d.get("kpi_date") if previous_1d else None,
            "reference_7d_kpi_date": previous_7d.get("kpi_date") if previous_7d else None,
        },
        "metrics": metric_rows,
        "disclaimer": "Operational KPI intelligence for monitoring and planning; not legal certification.",
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    lines = [
        "KPI Trend Report (24h / 7d)",
        f"Generated (UTC): {report['context']['generated_at']}",
        f"Base URL: {args.base_url}",
        f"Current KPI date: {report['context']['current_kpi_date']}",
        f"Reference 24h KPI date: {report['context']['reference_1d_kpi_date']}",
        f"Reference 7d KPI date: {report['context']['reference_7d_kpi_date']}",
        "",
    ]
    for item in metric_rows:
        lines.append(
            f"- {item['metric']}: current={item['current']} {item['unit']}, "
            f"d24h={item['delta_24h']} ({item['trend_24h']}), "
            f"d7d={item['delta_7d']} ({item['trend_7d']})"
        )
    lines.append("")
    lines.append(f"JSON: {json_path}")
    lines.append("Disclaimer: Operational KPI intelligence only; not legal certification.")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote report: {txt_path}")
    print(f"Wrote report: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
