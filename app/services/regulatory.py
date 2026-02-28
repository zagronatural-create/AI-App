from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.audit import append_audit_event
from app.services.compliance import normalize_parameter_code

ALLOWED_STANDARDS = {"FSSAI", "EU", "CODEX", "HACCP_INTERNAL"}
ALLOWED_REVIEW_STATUS = {"draft", "approved", "published", "rejected"}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
STANDARD_REQUIREMENT_COLUMNS = {
    "FSSAI": "require_fssai",
    "EU": "require_eu",
    "CODEX": "require_codex",
    "HACCP_INTERNAL": "require_haccp_internal",
}
UNIT_ALIASES = {
    "%": "%",
    "percent": "%",
    "percentage": "%",
    "ppb": "ug/kg",
    "ug/kg": "ug/kg",
    "µg/kg": "ug/kg",
    "μg/kg": "ug/kg",
    "mcg/kg": "ug/kg",
    "ppm": "mg/kg",
    "mg/kg": "mg/kg",
    "cfu/g": "cfu/g",
    "cfu per g": "cfu/g",
    "cfu/25g": "cfu/25g",
    "cfu per 25g": "cfu/25g",
    "absence/25g": "cfu/25g",
    "absent/25g": "cfu/25g",
}


def _parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid date format '{value}'. Use YYYY-MM-DD.") from exc


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value '{value}'") from exc


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def normalize_unit(raw_unit: str) -> str:
    cleaned = _clean_text(raw_unit)
    if not cleaned:
        return ""
    lowered = cleaned.lower().replace("μ", "µ")
    compact = " ".join(lowered.split())
    canonical = UNIT_ALIASES.get(compact)
    if canonical:
        return canonical
    return compact


def _requirements_table_exists(db: Session) -> bool:
    exists = db.execute(text("SELECT to_regclass('public.regulatory_parameter_requirements') IS NOT NULL")).scalar_one()
    return bool(exists)


def parse_threshold_csv(content: bytes) -> tuple[list[dict], list[str]]:
    required_cols = {"product_category", "parameter_name", "unit"}
    optional_cols = {"parameter_code", "limit_min", "limit_max", "severity", "source_clause", "remarks"}

    decoded = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    headers = {h.strip().lower() for h in reader.fieldnames if h}
    missing = required_cols - headers
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    unknown = headers - required_cols - optional_cols
    if unknown:
        raise ValueError(f"CSV has unsupported columns: {sorted(unknown)}")

    rows: list[dict] = []
    errors: list[str] = []

    for row_num, raw in enumerate(reader, start=2):
        normalized = {
            (k.strip().lower() if isinstance(k, str) else k): v for k, v in raw.items() if isinstance(k, str)
        }
        product_category = _clean_text(normalized.get("product_category"))
        parameter_name = _clean_text(normalized.get("parameter_name"))
        unit_raw = _clean_text(normalized.get("unit"))
        unit = normalize_unit(unit_raw)
        parameter_code = _clean_text(normalized.get("parameter_code")) or normalize_parameter_code(parameter_name)
        parameter_code = normalize_parameter_code(parameter_code)

        if not product_category:
            errors.append(f"Row {row_num}: product_category is required")
        if not parameter_name:
            errors.append(f"Row {row_num}: parameter_name is required")
        if not unit:
            errors.append(f"Row {row_num}: unit is required")

        try:
            limit_min = _parse_decimal(normalized.get("limit_min"))
            limit_max = _parse_decimal(normalized.get("limit_max"))
        except ValueError as exc:
            errors.append(f"Row {row_num}: {exc}")
            continue

        if limit_min is None and limit_max is None:
            errors.append(f"Row {row_num}: at least one of limit_min/limit_max is required")
            continue

        severity = (_clean_text(normalized.get("severity")) or "critical").lower()
        if severity not in ALLOWED_SEVERITIES:
            errors.append(f"Row {row_num}: severity must be one of {sorted(ALLOWED_SEVERITIES)}")
            continue
        source_clause = _clean_text(normalized.get("source_clause")) or None
        if not source_clause:
            errors.append(f"Row {row_num}: source_clause is required for authoritative traceability")
            continue
        remarks = _clean_text(normalized.get("remarks")) or None

        rows.append(
            {
                "product_category": product_category,
                "parameter_code": parameter_code,
                "parameter_name": parameter_name,
                "limit_min": limit_min,
                "limit_max": limit_max,
                "unit": unit,
                "unit_raw": unit_raw,
                "severity": severity,
                "source_clause": source_clause,
                "remarks": remarks,
            }
        )

    dedupe = set()
    deduped_rows = []
    for row in rows:
        key = (row["product_category"], row["parameter_code"])
        if key in dedupe:
            errors.append(
                f"Duplicate threshold key in CSV: product_category={row['product_category']}, "
                f"parameter_code={row['parameter_code']}"
            )
            continue
        dedupe.add(key)
        deduped_rows.append(row)

    return deduped_rows, errors


def _active_requirement_rows(
    db: Session,
    *,
    as_of: date,
    product_category: str | None = None,
) -> list[dict]:
    if not _requirements_table_exists(db):
        return []
    where = [
        "is_mandatory = true",
        "effective_from <= :as_of",
        "(effective_to IS NULL OR effective_to >= :as_of)",
    ]
    params: dict[str, object] = {"as_of": as_of}
    if product_category:
        where.append("product_category = :product_category")
        params["product_category"] = product_category

    query = f"""
        SELECT
          requirement_id::text AS requirement_id,
          product_category,
          parameter_code,
          parameter_name,
          canonical_unit,
          require_fssai,
          require_eu,
          require_codex,
          require_haccp_internal,
          effective_from,
          effective_to,
          source_note
        FROM regulatory_parameter_requirements
        WHERE {' AND '.join(where)}
        ORDER BY product_category, parameter_code
    """
    rows = db.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]


def _is_standard_required(requirement_row: dict, standard_name: str) -> bool:
    col = STANDARD_REQUIREMENT_COLUMNS.get(standard_name.upper())
    if not col:
        return False
    return bool(requirement_row.get(col))


def release_coverage_report(db: Session, *, release_id: str) -> dict:
    release = _require_release(db, release_id)
    release_rows = db.execute(
        text(
            """
            SELECT product_category, parameter_code, parameter_name, unit, source_clause
            FROM regulatory_threshold_values
            WHERE release_id = :release_id
            ORDER BY product_category, parameter_code
            """
        ),
        {"release_id": release_id},
    ).mappings().all()

    if not release_rows:
        return {
            "release_id": release_id,
            "standard_name": release["standard_name"],
            "ready_for_approval": False,
            "ready_for_publish": False,
            "missing_required": [{"message": "Release has no threshold rows"}],
            "unit_mismatches": [],
            "missing_source_clause": [],
            "extra_rows": [],
        }

    requirements = _active_requirement_rows(db, as_of=release["effective_from"])
    standard = str(release["standard_name"]).upper()
    required = [r for r in requirements if _is_standard_required(r, standard)]

    release_index = {(r["product_category"], r["parameter_code"]): dict(r) for r in release_rows}
    required_index = {(r["product_category"], r["parameter_code"]): dict(r) for r in required}

    missing_required: list[dict] = []
    unit_mismatches: list[dict] = []
    for key, req in required_index.items():
        row = release_index.get(key)
        if not row:
            missing_required.append(
                {
                    "product_category": req["product_category"],
                    "parameter_code": req["parameter_code"],
                    "parameter_name": req["parameter_name"],
                    "canonical_unit": req["canonical_unit"],
                }
            )
            continue
        if normalize_unit(str(row["unit"])) != normalize_unit(str(req["canonical_unit"])):
            unit_mismatches.append(
                {
                    "product_category": req["product_category"],
                    "parameter_code": req["parameter_code"],
                    "expected_unit": req["canonical_unit"],
                    "release_unit": row["unit"],
                }
            )

    missing_source_clause = [
        {
            "product_category": r["product_category"],
            "parameter_code": r["parameter_code"],
            "parameter_name": r["parameter_name"],
        }
        for r in release_rows
        if not _clean_text(r.get("source_clause"))
    ]
    extra_rows = [
        {
            "product_category": r["product_category"],
            "parameter_code": r["parameter_code"],
            "parameter_name": r["parameter_name"],
        }
        for key, r in release_index.items()
        if key not in required_index and required_index
    ]

    product_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"required": 0, "present": 0, "missing": 0})
    for req in required:
        category = req["product_category"]
        product_summary[category]["required"] += 1
        key = (req["product_category"], req["parameter_code"])
        if key in release_index:
            product_summary[category]["present"] += 1
        else:
            product_summary[category]["missing"] += 1

    ready = not missing_required and not unit_mismatches and not missing_source_clause
    return {
        "release_id": release_id,
        "standard_name": standard,
        "release_code": release["release_code"],
        "effective_from": str(release["effective_from"]),
        "effective_to": str(release["effective_to"]) if release["effective_to"] else None,
        "requirement_rows": len(required),
        "release_rows": len(release_rows),
        "ready_for_approval": ready,
        "ready_for_publish": ready,
        "missing_required": missing_required,
        "unit_mismatches": unit_mismatches,
        "missing_source_clause": missing_source_clause,
        "extra_rows": extra_rows,
        "product_category_summary": dict(product_summary),
        "disclaimer": "Coverage checks assist validation and documentation, not legal certification.",
    }


def active_coverage_report(db: Session, *, as_of: date | None = None, product_category: str | None = None) -> dict:
    effective_as_of = as_of or date.today()
    requirements = _active_requirement_rows(db, as_of=effective_as_of, product_category=product_category)
    if not requirements:
        return {
            "as_of": str(effective_as_of),
            "rows": [],
            "summary": {"requirement_rows": 0, "fully_covered_rows": 0},
            "disclaimer": "Coverage checks assist validation and documentation, not legal certification.",
        }

    active_threshold_rows = db.execute(
        text(
            """
            SELECT product_category, parameter_code, standard_name, unit
            FROM compliance_thresholds
            WHERE effective_from <= :as_of
              AND (effective_to IS NULL OR effective_to >= :as_of)
            """
        ),
        {"as_of": effective_as_of},
    ).mappings().all()

    threshold_index = {
        (r["product_category"], r["parameter_code"], r["standard_name"]): normalize_unit(str(r["unit"]))
        for r in active_threshold_rows
    }

    row_results = []
    fully_covered = 0
    for req in requirements:
        std_coverage = {}
        all_required_present = True
        for std in sorted(ALLOWED_STANDARDS):
            required_for_std = _is_standard_required(req, std)
            key = (req["product_category"], req["parameter_code"], std)
            observed_unit = threshold_index.get(key)
            present = (not required_for_std) or (observed_unit is not None)
            unit_ok = (not required_for_std) or (observed_unit == normalize_unit(str(req["canonical_unit"])))
            if required_for_std and (not present or not unit_ok):
                all_required_present = False
            std_coverage[std] = {
                "required": required_for_std,
                "present": present,
                "unit_ok": unit_ok,
                "observed_unit": observed_unit,
            }

        if all_required_present:
            fully_covered += 1

        row_results.append(
            {
                "product_category": req["product_category"],
                "parameter_code": req["parameter_code"],
                "parameter_name": req["parameter_name"],
                "canonical_unit": req["canonical_unit"],
                "standards": std_coverage,
                "fully_covered": all_required_present,
            }
        )

    return {
        "as_of": str(effective_as_of),
        "rows": row_results,
        "summary": {
            "requirement_rows": len(row_results),
            "fully_covered_rows": fully_covered,
            "coverage_pct": round((fully_covered / len(row_results)) * 100.0, 2) if row_results else 0.0,
        },
        "disclaimer": "Coverage checks assist validation and documentation, not legal certification.",
    }


def list_parameter_requirements(
    db: Session,
    *,
    as_of: date | None = None,
    product_category: str | None = None,
) -> dict:
    effective_as_of = as_of or date.today()
    rows = _active_requirement_rows(db, as_of=effective_as_of, product_category=product_category)
    return {
        "as_of": str(effective_as_of),
        "rows": rows,
        "summary": {"rows": len(rows)},
        "disclaimer": "Requirement profile supports validation coverage; not legal certification.",
    }


def _validate_rows_against_requirements(
    db: Session,
    *,
    standard_name: str,
    effective_from: date,
    rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    if not _requirements_table_exists(db):
        raise ValueError(
            "Coverage profile table 'regulatory_parameter_requirements' is missing. "
            "Apply migrations 011 and 012 before importing authoritative releases."
        )
    requirements = _active_requirement_rows(db, as_of=effective_from)
    required = [r for r in requirements if _is_standard_required(r, standard_name)]
    if not required:
        raise ValueError(
            f"No active mandatory requirement rows configured for standard={standard_name} "
            f"at effective_from={effective_from}. Configure regulatory_parameter_requirements first."
        )

    req_index = {(r["product_category"], r["parameter_code"]): r for r in required}
    row_index = {(r["product_category"], r["parameter_code"]): r for r in rows}

    missing = []
    unit_mismatches = []
    for key, req in req_index.items():
        row = row_index.get(key)
        if not row:
            missing.append(
                {
                    "product_category": req["product_category"],
                    "parameter_code": req["parameter_code"],
                    "canonical_unit": req["canonical_unit"],
                }
            )
            continue
        if normalize_unit(str(row["unit"])) != normalize_unit(str(req["canonical_unit"])):
            unit_mismatches.append(
                {
                    "product_category": req["product_category"],
                    "parameter_code": req["parameter_code"],
                    "expected_unit": req["canonical_unit"],
                    "provided_unit": row["unit"],
                }
            )
    return missing, unit_mismatches


def import_threshold_release(
    db: Session,
    *,
    standard_name: str,
    release_code: str,
    document_title: str,
    effective_from: str,
    imported_by: str,
    csv_bytes: bytes,
    jurisdiction: str | None = None,
    source_authority: str | None = None,
    document_url: str | None = None,
    publication_date: str | None = None,
    effective_to: str | None = None,
    notes: str | None = None,
) -> dict:
    standard = _clean_text(standard_name).upper()
    if standard not in ALLOWED_STANDARDS:
        raise ValueError(f"standard_name must be one of {sorted(ALLOWED_STANDARDS)}")

    release_code = _clean_text(release_code)
    if not release_code:
        raise ValueError("release_code is required")

    document_title = _clean_text(document_title)
    if not document_title:
        raise ValueError("document_title is required")

    eff_from = _parse_iso_date(effective_from)
    if not eff_from:
        raise ValueError("effective_from is required")

    eff_to = _parse_iso_date(effective_to)
    if eff_to and eff_to < eff_from:
        raise ValueError("effective_to cannot be earlier than effective_from")

    authority = _clean_text(source_authority)
    if not authority:
        raise ValueError("source_authority is required for authoritative regulatory imports")

    pub_date = _parse_iso_date(publication_date)
    if not pub_date:
        raise ValueError("publication_date is required for authoritative regulatory imports")

    rows, errors = parse_threshold_csv(csv_bytes)
    if errors:
        preview = "; ".join(errors[:8])
        more = "" if len(errors) <= 8 else f" (+{len(errors) - 8} more)"
        raise ValueError(f"CSV validation failed: {preview}{more}")
    if not rows:
        raise ValueError("CSV has no valid threshold rows")

    missing_required, unit_mismatches = _validate_rows_against_requirements(
        db,
        standard_name=standard,
        effective_from=eff_from,
        rows=rows,
    )
    if missing_required or unit_mismatches:
        messages = []
        if missing_required:
            preview_missing = ", ".join(
                f"{m['product_category']}:{m['parameter_code']}" for m in missing_required[:6]
            )
            suffix = "" if len(missing_required) <= 6 else f" (+{len(missing_required) - 6} more)"
            messages.append(f"missing required parameters: {preview_missing}{suffix}")
        if unit_mismatches:
            preview_mismatch = ", ".join(
                (
                    f"{m['product_category']}:{m['parameter_code']} expected {m['expected_unit']} "
                    f"got {m['provided_unit']}"
                )
                for m in unit_mismatches[:6]
            )
            suffix = "" if len(unit_mismatches) <= 6 else f" (+{len(unit_mismatches) - 6} more)"
            messages.append(f"unit mismatches: {preview_mismatch}{suffix}")
        raise ValueError("Coverage validation failed: " + "; ".join(messages))

    release_id = str(uuid.uuid4())
    try:
        db.execute(
            text(
                """
                INSERT INTO regulatory_threshold_releases (
                  release_id, standard_name, release_code, jurisdiction, source_authority,
                  document_title, document_url, publication_date, effective_from, effective_to,
                  review_status, imported_by, imported_at, notes, row_count
                ) VALUES (
                  :release_id, :standard_name, :release_code, :jurisdiction, :source_authority,
                  :document_title, :document_url, :publication_date, :effective_from, :effective_to,
                  'draft', :imported_by, now(), :notes, :row_count
                )
                """
            ),
            {
                "release_id": release_id,
                "standard_name": standard,
                "release_code": release_code,
                "jurisdiction": _clean_text(jurisdiction) or None,
                "source_authority": authority,
                "document_title": document_title,
                "document_url": _clean_text(document_url) or None,
                "publication_date": pub_date,
                "effective_from": eff_from,
                "effective_to": eff_to,
                "imported_by": imported_by,
                "notes": _clean_text(notes) or None,
                "row_count": len(rows),
            },
        )
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"release_code '{release_code}' already exists") from exc

    for row in rows:
        db.execute(
            text(
                """
                INSERT INTO regulatory_threshold_values (
                  value_id, release_id, product_category, parameter_code, parameter_name,
                  limit_min, limit_max, unit, severity, source_clause, remarks
                ) VALUES (
                  :value_id, :release_id, :product_category, :parameter_code, :parameter_name,
                  :limit_min, :limit_max, :unit, :severity, :source_clause, :remarks
                )
                """
            ),
            {
                "value_id": uuid.uuid4(),
                "release_id": release_id,
                "product_category": row["product_category"],
                "parameter_code": row["parameter_code"],
                "parameter_name": row["parameter_name"],
                "limit_min": row["limit_min"],
                "limit_max": row["limit_max"],
                "unit": row["unit"],
                "severity": row["severity"],
                "source_clause": row["source_clause"],
                "remarks": row["remarks"],
            },
        )

    append_audit_event(
        db,
        actor_id=imported_by,
        action_type="REG_THRESHOLD_RELEASE_IMPORTED",
        entity_type="regulatory_release",
        entity_id=release_id,
        payload={
            "standard_name": standard,
            "release_code": release_code,
            "effective_from": str(eff_from),
            "effective_to": str(eff_to) if eff_to else None,
            "row_count": len(rows),
            "document_title": document_title,
            "source_authority": authority,
            "publication_date": str(pub_date),
        },
    )
    db.commit()

    normalized_units = sum(1 for row in rows if normalize_unit(row["unit_raw"]) != row["unit"])

    return {
        "release_id": release_id,
        "standard_name": standard,
        "release_code": release_code,
        "review_status": "draft",
        "row_count": len(rows),
        "effective_from": str(eff_from),
        "effective_to": str(eff_to) if eff_to else None,
        "normalized_unit_rows": normalized_units,
        "disclaimer": "Imported regulatory data supports AI-assisted validation; not legal certification.",
    }


def list_threshold_releases(db: Session, *, limit: int = 100, standard_name: str | None = None) -> list[dict]:
    params: dict[str, object] = {"limit": limit}
    where = ""
    if standard_name:
        where = "WHERE standard_name = :standard_name"
        params["standard_name"] = standard_name.upper().strip()

    rows = db.execute(
        text(
            f"""
            SELECT release_id::text AS release_id, standard_name, release_code, document_title,
                   source_authority, publication_date, effective_from, effective_to, review_status,
                   imported_by, imported_at, approved_by, approved_at, published_by, published_at,
                   notes, row_count
            FROM regulatory_threshold_releases
            {where}
            ORDER BY imported_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return [dict(r) for r in rows]


def get_threshold_release(db: Session, release_id: str) -> dict | None:
    release = db.execute(
        text(
            """
            SELECT release_id::text AS release_id, standard_name, release_code, jurisdiction,
                   source_authority, document_title, document_url, publication_date,
                   effective_from, effective_to, review_status, imported_by, imported_at,
                   approved_by, approved_at, published_by, published_at, notes, row_count
            FROM regulatory_threshold_releases
            WHERE release_id = :release_id
            """
        ),
        {"release_id": release_id},
    ).mappings().first()
    if not release:
        return None

    rows = db.execute(
        text(
            """
            SELECT value_id::text AS value_id, product_category, parameter_code, parameter_name,
                   limit_min, limit_max, unit, severity, source_clause, remarks
            FROM regulatory_threshold_values
            WHERE release_id = :release_id
            ORDER BY product_category, parameter_code
            """
        ),
        {"release_id": release_id},
    ).mappings().all()

    return {"release": dict(release), "threshold_rows": [dict(r) for r in rows]}


def _require_release(db: Session, release_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT release_id::text AS release_id, standard_name, release_code,
                   effective_from, effective_to, review_status, row_count
            FROM regulatory_threshold_releases
            WHERE release_id = :release_id
            """
        ),
        {"release_id": release_id},
    ).mappings().first()
    if not row:
        raise ValueError("Release not found")
    status = str(row["review_status"])
    if status not in ALLOWED_REVIEW_STATUS:
        raise ValueError(f"Invalid release status in DB: {status}")
    return dict(row)


def approve_threshold_release(db: Session, *, release_id: str, approved_by: str, notes: str | None = None) -> dict:
    release = _require_release(db, release_id)
    if release["review_status"] == "published":
        raise ValueError("Release is already published and cannot be re-approved")
    if release["review_status"] == "approved":
        return {"release_id": release_id, "review_status": "approved", "idempotent": True}

    coverage = release_coverage_report(db, release_id=release_id)
    if not coverage["ready_for_approval"]:
        raise ValueError(
            "Release cannot be approved until coverage is complete and units/source clauses are valid. "
            f"missing_required={len(coverage['missing_required'])}, "
            f"unit_mismatches={len(coverage['unit_mismatches'])}, "
            f"missing_source_clause={len(coverage['missing_source_clause'])}"
        )

    db.execute(
        text(
            """
            UPDATE regulatory_threshold_releases
            SET review_status = 'approved',
                approved_by = :approved_by,
                approved_at = now(),
                notes = COALESCE(:notes, notes)
            WHERE release_id = :release_id
            """
        ),
        {"release_id": release_id, "approved_by": approved_by, "notes": _clean_text(notes) or None},
    )

    append_audit_event(
        db,
        actor_id=approved_by,
        action_type="REG_THRESHOLD_RELEASE_APPROVED",
        entity_type="regulatory_release",
        entity_id=release_id,
        payload={"release_id": release_id, "release_code": release["release_code"]},
    )
    db.commit()
    return {"release_id": release_id, "review_status": "approved", "idempotent": False}


def publish_threshold_release(db: Session, *, release_id: str, published_by: str) -> dict:
    release = _require_release(db, release_id)
    if release["review_status"] != "approved":
        raise ValueError("Release must be approved before publish")

    coverage = release_coverage_report(db, release_id=release_id)
    if not coverage["ready_for_publish"]:
        raise ValueError(
            "Release cannot be published until coverage is complete and units/source clauses are valid. "
            f"missing_required={len(coverage['missing_required'])}, "
            f"unit_mismatches={len(coverage['unit_mismatches'])}, "
            f"missing_source_clause={len(coverage['missing_source_clause'])}"
        )

    rows = db.execute(
        text(
            """
            SELECT product_category, parameter_code, parameter_name, limit_min, limit_max, unit, severity, source_clause
            FROM regulatory_threshold_values
            WHERE release_id = :release_id
            ORDER BY product_category, parameter_code
            """
        ),
        {"release_id": release_id},
    ).mappings().all()
    if not rows:
        raise ValueError("Release has no threshold rows to publish")

    effective_from: date = release["effective_from"]
    effective_to: date | None = release["effective_to"]
    close_date = effective_from - timedelta(days=1)

    closed = db.execute(
        text(
            """
            UPDATE compliance_thresholds c
            SET effective_to = :close_date
            WHERE c.standard_name = :standard_name
              AND c.effective_to IS NULL
              AND c.effective_from <= :effective_from
              AND EXISTS (
                SELECT 1
                FROM regulatory_threshold_values r
                WHERE r.release_id = :release_id
                  AND r.product_category = c.product_category
                  AND r.parameter_code = c.parameter_code
              )
            """
        ),
        {
            "close_date": close_date,
            "standard_name": release["standard_name"],
            "effective_from": effective_from,
            "release_id": release_id,
        },
    ).rowcount or 0

    inserted = 0
    for row in rows:
        source_ref = release["release_code"]
        if row["source_clause"]:
            source_ref = f"{source_ref}:{row['source_clause']}"

        db.execute(
            text(
                """
                INSERT INTO compliance_thresholds (
                  threshold_id, parameter_code, standard_name, product_category,
                  limit_min, limit_max, unit, severity, effective_from, effective_to, source_ref
                ) VALUES (
                  :threshold_id, :parameter_code, :standard_name, :product_category,
                  :limit_min, :limit_max, :unit, :severity, :effective_from, :effective_to, :source_ref
                )
                """
            ),
            {
                "threshold_id": uuid.uuid4(),
                "parameter_code": row["parameter_code"],
                "standard_name": release["standard_name"],
                "product_category": row["product_category"],
                "limit_min": row["limit_min"],
                "limit_max": row["limit_max"],
                "unit": row["unit"],
                "severity": row["severity"],
                "effective_from": effective_from,
                "effective_to": effective_to,
                "source_ref": source_ref,
            },
        )
        inserted += 1

    db.execute(
        text(
            """
            UPDATE regulatory_threshold_releases
            SET review_status = 'published',
                published_by = :published_by,
                published_at = now()
            WHERE release_id = :release_id
            """
        ),
        {"release_id": release_id, "published_by": published_by},
    )

    append_audit_event(
        db,
        actor_id=published_by,
        action_type="REG_THRESHOLD_RELEASE_PUBLISHED",
        entity_type="regulatory_release",
        entity_id=release_id,
        payload={
            "release_id": release_id,
            "standard_name": release["standard_name"],
            "release_code": release["release_code"],
            "closed_previous_rows": closed,
            "inserted_rows": inserted,
            "effective_from": str(effective_from),
            "effective_to": str(effective_to) if effective_to else None,
        },
    )
    db.commit()

    return {
        "release_id": release_id,
        "review_status": "published",
        "closed_previous_rows": closed,
        "inserted_rows": inserted,
        "effective_from": str(effective_from),
        "effective_to": str(effective_to) if effective_to else None,
        "disclaimer": "Published thresholds support operational validation and do not grant legal certification.",
    }


def release_summary_for_ui(db: Session, *, limit: int = 20) -> dict:
    rows = list_threshold_releases(db, limit=limit)
    coverage = active_coverage_report(db)
    return {
        "rows": rows,
        "standards_supported": sorted(ALLOWED_STANDARDS),
        "coverage_summary": coverage.get("summary", {}),
        "note": "Real regulatory sources must be reviewed and approved before publish.",
    }
