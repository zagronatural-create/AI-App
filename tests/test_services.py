from app.services.compliance import _convert_value, evaluate_status, normalize_parameter_code, parse_lab_text
from app.services.ccp import _is_near, _is_outside
from app.services.regulatory import normalize_unit, parse_threshold_csv
from app.services.risk import _matrix_zone, _supplier_metric_band, batch_risk_score, supplier_risk_score


def test_parse_lab_text_extracts_rows():
    raw = "Moisture: 8.4 %\nAflatoxin B1 = 4 ppb"
    rows = parse_lab_text(raw)
    assert len(rows) == 2
    assert rows[0]["parameter_name"] == "Moisture"


def test_evaluate_status_warning_near_upper_limit():
    status, risk = evaluate_status(8.4, None, 8.5)
    assert status == "WARNING"
    assert risk == "NEAR_UPPER_LIMIT"


def test_supplier_risk_score_high_band():
    features = {
        "delay_rate_90d": 0.5,
        "quality_fail_rate_180d": 0.3,
        "rejection_rate": 0.2,
        "volume_cv": 0.6,
        "critical_nonconformities_12m": 3,
    }
    result = supplier_risk_score(features)
    assert result["risk_band"] in {"MEDIUM", "HIGH"}
    assert 0 <= result["risk_score"] <= 100


def test_normalize_parameter_code_aliases():
    assert normalize_parameter_code("Aflatoxin B1") == "AFLA_B1"
    assert normalize_parameter_code("Total Aflatoxins") == "AFLA_TOTAL"
    assert normalize_parameter_code("Total Plate Count") == "TPC"


def test_ccp_threshold_flags():
    assert _is_outside(70.0, 55, 65) is True
    assert _is_outside(60.0, 55, 65) is False
    assert _is_near(64.0, 55, 65, 10) is True
    assert _is_near(60.0, 55, 65, 10) is True


def test_batch_risk_score_outputs_band():
    result = batch_risk_score(
        {
            "supplier_risk_norm": 0.8,
            "storage_days_norm": 0.2,
            "open_alerts_norm": 0.4,
            "historical_deviation_rate": 0.3,
            "current_fail_count_norm": 0.2,
        }
    )
    assert result["risk_band"] in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= result["risk_score"] <= 100


def test_supplier_metric_band_thresholds():
    assert _supplier_metric_band("delay_rate_90d", 0.02) == "LOW"
    assert _supplier_metric_band("delay_rate_90d", 0.09) == "MEDIUM"
    assert _supplier_metric_band("delay_rate_90d", 0.2) == "HIGH"
    assert _supplier_metric_band("volume_cv", 0.1) == "LOW"
    assert _supplier_metric_band("volume_cv", 0.25) == "MEDIUM"
    assert _supplier_metric_band("volume_cv", 0.5) == "HIGH"


def test_matrix_zone_classification():
    assert _matrix_zone(0.8, 70) == "CRITICAL"
    assert _matrix_zone(0.55, 60) == "HIGH"
    assert _matrix_zone(0.4, 20) == "MEDIUM"
    assert _matrix_zone(0.2, 20) == "LOW"


def test_normalize_unit_aliases():
    assert normalize_unit("ppb") == "ug/kg"
    assert normalize_unit("ppm") == "mg/kg"
    assert normalize_unit("CFU/25g") == "cfu/25g"
    assert normalize_unit("%") == "%"


def test_parse_threshold_csv_requires_source_clause_and_normalizes_units():
    content = (
        "product_category,parameter_name,parameter_code,unit,limit_max,severity,source_clause\n"
        "TRAD-NUTRI-500G,Aflatoxin B1,AFLA_B1,ppb,2,critical,Clause 4.2\n"
    ).encode("utf-8")
    rows, errors = parse_threshold_csv(content)
    assert not errors
    assert len(rows) == 1
    assert rows[0]["unit"] == "ug/kg"

    bad = (
        "product_category,parameter_name,parameter_code,unit,limit_max,severity\n"
        "TRAD-NUTRI-500G,Aflatoxin B1,AFLA_B1,ppb,2,critical\n"
    ).encode("utf-8")
    _, bad_errors = parse_threshold_csv(bad)
    assert any("source_clause is required" in e for e in bad_errors)


def test_unit_conversion_between_ugkg_and_mgkg():
    assert _convert_value(1000.0, "ug/kg", "mg/kg") == 1.0
    assert _convert_value(0.1, "mg/kg", "ug/kg") == 100.0
    assert _convert_value(5.0, "%", "mg/kg") is None
