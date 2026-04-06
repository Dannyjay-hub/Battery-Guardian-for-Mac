"""Battery Guardian — shared constants.

Scoring model
─────────────
Each forensic check contributes a weighted penalty score if triggered.
The weights reflect our confidence that each signal is exclusively produced
by spoofed hardware and cannot appear on genuine batteries under normal use.

  SCORE_THRESHOLD_SPOOFED: minimum total score to render a SPOOFED verdict.
  Currently set to 40 — a single high-confidence check is sufficient.
"""

import os

VERSION = "1.3"
PORT = 8080
HISTORY_FILE = os.path.expanduser("~/.battery_guardian_log.json")
MAX_HISTORY = 100

# ── Forensic scoring weights ──────────────────────────────────────────────────
# Each weight is the penalty added to the score when a check fails.
# Checks are ordered by conviction strength (highest = most definitive signal).

SCORE_CLOCK_INTEGRITY = 50      # Two independent time counters disagree ≥20%
                                 # Impossible on genuine hardware (verified: 0.005% real-world)

SCORE_CALIBRATION_PARADOX = 50  # CycleCountLastQmax > CycleCount
                                 # Mathematically impossible without cycle counter reset

SCORE_ZERO_ENTROPY = 40         # All Qmax cell values identical after 5+ cycles
                                 # IT algorithm produces natural variance on any real cell

SCORE_FROZEN_CLOCK = 40         # TotalOperatingTime unchanged 30h+ between scans
                                 # Genuine chips accumulate hours continuously

SCORE_LAZY_CLONE = 30           # Qmax[0] == DesignCapacity after 5+ cycles
                                 # Most common DataFlash spoof pattern

SCORE_CALIBRATION_TAMPERING = 30 # DOD0 == DesignCapacity — fabricated calibration record

SCORE_CHIP_ORIGIN = 30          # MaximumPackVoltage < 9,000 mV (below 3-cell CUV floor)
                                 # Chip came from a 2-cell device (phone/tablet)

SCORE_INTERNAL_RESISTANCE = 25  # Qmax ≈ FCC (< 1% gap) at cycles > 30
                                 # Real batteries always develop an impedance gap with use

SCORE_THRESHOLD_SPOOFED = 40    # Verdict threshold: scores ≥ 40 → SPOOFED
