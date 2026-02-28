from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session


def parse_lab_text(raw_text: str) -> list[dict]:
    """Simple parameter extraction fallback before full OCR/NLP pipeline."""
    pattern = re.compile(r"(?P<param>[A-Za-z0-9_\- ]+)\s*[:=]\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[%a-zA-Z/]+)")
    extracted = []
    for match in pattern.finditer(raw_text):
        parameter_name = match.group("param").strip()
        extracted.append(
            {
                "parameter_name": parameter_name,
                "parameter_code": normalize_parameter_code(parameter_name),
                "observed_value": float(match.group("value")),
                "unit": match.group("unit"),
            }
        )
    return extracted


def normalize_parameter_code(parameter_name: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", parameter_name.strip().upper()).strip("_")
    aliases = {
        "MOISTURE": "MOISTURE",
        "AFLATOXIN_B1": "AFLA_B1",
        "AFLA_B1": "AFLA_B1",
        "TOTAL_PLATE_COUNT": "TPC",
    }
    return aliases.get(key, key)


def _format_limit(limit_min: Decimal | None, limit_max: Decimal | None, unit: str) -> str | None:
    if limit_min is None and limit_max is None:
        return None
    if limit_min is not None and limit_max is not None:
        return f"{limit_min:g} to {limit_max:g} {unit}"
    if limit_max is not None:
        return f"<= {limit_max:g} {unit}"
    return f">= {limit_min:g} {unit}"


def evaluate_status(observed: float, limit_min: Decimal | None, limit_max: Decimal | None) -> tuple[str, str]:
    status = "PASS"
    risk_flag = "NORMAL"

    if limit_min is not None and observed < float(limit_min):
        return "FAIL", "OUT_OF_RANGE"
    if limit_max is not None and observed > float(limit_max):
        return "FAIL", "OUT_OF_RANGE"

    near_margin = 0.1
    if limit_max is not None and observed >= float(limit_max) * (1 - near_margin):
        risk_flag = "NEAR_UPPER_LIMIT"
    if limit_min is not None and observed <= float(limit_min) * (1 + near_margin):
        risk_flag = "NEAR_LOWER_LIMIT"
    if risk_flag != "NORMAL":
        status = "WARNING"

    return status, risk_flag


def batch_comparison(db: Session, batch_code: str) -> list[dict]:
    query = text(
        """
        SELECT q.parameter_name, q.parameter_code, q.observed_value, q.unit,
               t.standard_name, t.limit_min, t.limit_max, t.unit AS limit_unit
        FROM quality_test_records q
        JOIN production_batches b ON b.batch_id = q.batch_id
        LEFT JOIN compliance_thresholds t
          ON t.parameter_code = q.parameter_code
         AND t.product_category = b.product_sku
         AND t.effective_from <= COALESCE(q.tested_at::date, current_date)
         AND (t.effective_to IS NULL OR t.effective_to >= COALESCE(q.tested_at::date, current_date))
        WHERE b.batch_code = :batch_code
        ORDER BY q.parameter_name;
        """
    )
    rows = db.execute(query, {"batch_code": batch_code}).mappings().all()

    grouped: dict[tuple[str, float, str], dict] = defaultdict(dict)
    for row in rows:
        key = (row["parameter_name"], float(row["observed_value"]), row["unit"])
        grouped[key][row["standard_name"]] = {
            "limit_min": row["limit_min"],
            "limit_max": row["limit_max"],
            "unit": row["limit_unit"] or row["unit"],
        }

    output = []
    for (parameter, observed, unit), standards in grouped.items():
        fssai = standards.get("FSSAI")
        eu = standards.get("EU")
        codex = standards.get("CODEX")
        haccp = standards.get("HACCP_INTERNAL")

        status_rollup = "PASS"
        risk_rollup = "NORMAL"
        for std in [fssai, eu, codex, haccp]:
            if not std:
                continue
            status, risk = evaluate_status(observed, std["limit_min"], std["limit_max"])
            if status == "FAIL":
                status_rollup = "FAIL"
                risk_rollup = risk
                break
            if status == "WARNING" and status_rollup != "FAIL":
                status_rollup = "WARNING"
                risk_rollup = risk

        output.append(
            {
                "parameter": parameter,
                "batch_value": observed,
                "unit": unit,
                "fssai_limit": _format_limit(
                    fssai["limit_min"], fssai["limit_max"], fssai["unit"]
                )
                if fssai
                else None,
                "eu_limit": _format_limit(eu["limit_min"], eu["limit_max"], eu["unit"]) if eu else None,
                "codex_limit": _format_limit(
                    codex["limit_min"], codex["limit_max"], codex["unit"]
                )
                if codex
                else None,
                "haccp_limit": _format_limit(
                    haccp["limit_min"], haccp["limit_max"], haccp["unit"]
                )
                if haccp
                else None,
                "status": status_rollup,
                "risk_flag": risk_rollup,
            }
        )

    return output
