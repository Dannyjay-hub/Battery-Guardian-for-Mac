import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from bg_forensics import evaluate_battery, load_contract


FIXTURE_DIR = Path(__file__).parents[1] / "forensics" / "fixtures"


def test_contract_fixture_expectations():
    contract = load_contract()
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        result = evaluate_battery(fixture["data"], contract)
        expected = fixture["expected"]
        assert result.profile == expected["profile"], path.name
        assert result.verdict == expected["verdict"], path.name
        assert result.score == expected["score"], path.name
        assert result.complete == expected["complete"], path.name


def test_identical_non_reset_dod0_is_not_a_failure():
    result = evaluate_battery({
        "DeviceName": "bq20z451",
        "CycleCount": 919,
        "DesignCapacity": 7150,
        "Qmax": [7019, 7006, 6998],
        "DOD0": [2208, 2208, 2208],
        "DataFlashWriteCount": 6820,
    })
    assert result.verdict == "NO_ANOMALIES"
    assert result.score == 0


def test_unknown_gauge_never_defaults_to_clean():
    result = evaluate_battery({"DeviceName": "unknown", "CycleCount": 100})
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert not result.complete


def test_missing_fields_never_default_to_clean():
    result = evaluate_battery({
        "DeviceName": "bq20z451",
        "CycleCount": 1,
        "DesignCapacity": 8940,
        "Qmax": [8960, 8980, 8970],
    })
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert set(result.missing_fields) == {"DOD0", "DataFlashWriteCount"}


def test_calibration_timeline_contradiction_is_scored():
    result = evaluate_battery({
        "DeviceName": "bq40z651",
        "CycleCount": 50,
        "DesignCapacity": 8579,
        "Qmax": [8500, 8490, 8510],
        "DOD0": [640, 650, 645],
        "DataFlashWriteCount": 9000,
        "TotalOperatingTime": 1000,
        "TemperatureSamples": 16000,
        "CycleCountLastQmax": 100,
        "MaximumPackVoltage": 13000,
    })
    assert result.verdict == "SPOOFED"
    assert result.score == 50
