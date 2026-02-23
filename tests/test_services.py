from app.services.compliance import evaluate_status, normalize_parameter_code, parse_lab_text
from app.services.ccp import _is_near, _is_outside
from app.services.risk import batch_risk_score, supplier_risk_score


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
