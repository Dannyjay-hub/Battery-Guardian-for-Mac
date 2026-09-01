"""Model-aware Battery Guardian forensic policy.

This module is intentionally pure: it accepts a normalized battery dictionary
and returns evidence. I/O, UI state, history persistence, and battery health are
handled elsewhere. The JSON contract is the authoritative policy description.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).with_name("forensics") / "contract.json"


@dataclass(frozen=True)
class Evidence:
    check_id: str
    title: str
    description: str
    status: str
    score: int = 0
    evidence_level: str = "unknown"


@dataclass(frozen=True)
class Evaluation:
    policy_version: str
    profile: str | None
    complete: bool
    missing_fields: tuple[str, ...]
    score: int
    verdict: str
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["missing_fields"] = list(self.missing_fields)
        value["evidence"] = [asdict(item) for item in self.evidence]
        return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_battery(data: dict[str, Any], contract: dict[str, Any] | None = None) -> Evaluation:
    contract = contract or load_contract()
    policy_version = contract["policy_version"]
    device_name = data.get("DeviceName")
    profile = contract["profiles"].get(device_name)

    if profile is None:
        evidence = Evidence(
            check_id="profile_support",
            title="Unsupported or unidentified gauge",
            description="Battery Guardian cannot select a validated gauge profile for this telemetry.",
            status="warning",
            evidence_level="exact-device-required",
        )
        return Evaluation(
            policy_version=policy_version,
            profile=None,
            complete=False,
            missing_fields=("DeviceName",) if not device_name else (),
            score=0,
            verdict="INSUFFICIENT_EVIDENCE",
            evidence=(evidence,),
        )

    missing = tuple(field for field in profile["minimum_fields"] if not _present(data, field))
    evidence: list[Evidence] = []
    if missing:
        evidence.append(Evidence(
            check_id="minimum_evidence",
            title="Insufficient forensic evidence",
            description="Required fields are missing: " + ", ".join(missing) + ". No authenticity conclusion was made.",
            status="warning",
            evidence_level="contract",
        ))

    score = 0
    active_checks = set(profile["active_checks"])

    if "bq20z451_reset_signature" in active_checks:
        rule = contract["checks"]["bq20z451_reset_signature"]
        dod0 = data.get("DOD0")
        cycles = data.get("CycleCount")
        writes = data.get("DataFlashWriteCount")
        if (
            isinstance(dod0, list)
            and len(dod0) == profile["cell_count"]
            and isinstance(cycles, int)
            and cycles > rule["minimum_cycles"]
            and all(value == rule["dod0_value"] for value in dod0)
            and writes == rule["dataflash_write_count"]
        ):
            points = int(rule["score"])
            score += points
            evidence.append(Evidence(
                check_id="bq20z451_reset_signature",
                title="Model-specific reset signature detected",
                description=(
                    f"The bq20z451 reports {cycles} cycles while all DOD0 cells remain at "
                    f"{rule['dod0_value']} and DataFlashWriteCount is zero. This is a strong "
                    "empirical reset/replacement signature, not a cryptographic provenance test."
                ),
                status="fail",
                score=points,
                evidence_level=rule["evidence_level"],
            ))

    if "calibration_timeline" in active_checks:
        last_qmax = data.get("CycleCountLastQmax")
        cycles = data.get("CycleCount")
        if isinstance(last_qmax, int) and isinstance(cycles, int):
            rule = contract["checks"]["calibration_timeline"]
            if last_qmax > cycles:
                points = int(rule["score"])
                score += points
                evidence.append(Evidence(
                    check_id="calibration_timeline",
                    title="Calibration timeline contradiction",
                    description=f"Last Qmax update cycle {last_qmax} exceeds current cycle count {cycles}.",
                    status="fail",
                    score=points,
                    evidence_level=rule["evidence_level"],
                ))
            else:
                evidence.append(Evidence(
                    check_id="calibration_timeline",
                    title="Calibration timeline consistent",
                    description=f"Last Qmax update cycle {last_qmax} does not exceed current cycle count {cycles}.",
                    status="success",
                    evidence_level=rule["evidence_level"],
                ))

    if "clock_integrity" in active_checks:
        samples = data.get("TemperatureSamples")
        operating_hours = data.get("TotalOperatingTime")
        if isinstance(samples, int) and isinstance(operating_hours, int) and operating_hours > 0:
            rule = contract["checks"]["clock_integrity"]
            if samples >= rule["minimum_temperature_samples"]:
                implied_hours = samples * rule["seconds_per_temperature_sample"] / 3600
                difference = abs(implied_hours - operating_hours) / max(implied_hours, operating_hours) * 100
                if difference >= rule["fail_difference_percent"]:
                    points = int(rule["score"])
                    score += points
                    evidence.append(Evidence(
                        check_id="clock_integrity",
                        title="Lifetime counters contradict each other",
                        description=f"The two counters differ by {difference:.1f}%, above the model policy threshold.",
                        status="fail",
                        score=points,
                        evidence_level=rule["evidence_level"],
                    ))
                elif difference < rule["pass_difference_percent"]:
                    evidence.append(Evidence(
                        check_id="clock_integrity",
                        title="Lifetime counters agree",
                        description=f"The two counters agree within {difference:.2f}%.",
                        status="success",
                        evidence_level=rule["evidence_level"],
                    ))
                else:
                    evidence.append(Evidence(
                        check_id="clock_integrity",
                        title="Lifetime counters need review",
                        description=f"The two counters differ by {difference:.1f}%, within the policy review band.",
                        status="warning",
                        evidence_level=rule["evidence_level"],
                    ))

    if score >= contract["spoofed_score_threshold"]:
        verdict = "SPOOFED"
    elif score > 0:
        verdict = "SUSPICIOUS"
    elif missing:
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "NO_ANOMALIES"
        evidence.append(Evidence(
            check_id="result_scope",
            title="No supported anomaly detected",
            description="The available supported checks found no contradiction. This does not prove Apple originality.",
            status="info",
            evidence_level="contract",
        ))

    return Evaluation(
        policy_version=policy_version,
        profile=device_name,
        complete=not missing,
        missing_fields=missing,
        score=score,
        verdict=verdict,
        evidence=tuple(evidence),
    )


def _present(data: dict[str, Any], field: str) -> bool:
    value = data.get(field)
    if value is None:
        return False
    if isinstance(value, (str, list, tuple, dict)) and not value:
        return False
    return True
