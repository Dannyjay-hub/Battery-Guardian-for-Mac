import pytest
import sys
import os
from datetime import datetime

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from bg_analysis import compute_health_score, compute_trends

# --- Health Score Tests ---

def test_genuine_battery_scores_high():
    data = {
        "CycleCount": 200,
        "AppleRawMaxCapacity": 4500,
        "DesignCapacity": 5000
    }
    # scan_score is the penalty from other spoofing metrics (0 = genuine)
    score = compute_health_score(data, scan_score=0)
    assert score >= 90

def test_spoofed_battery_scores_low():
    data = {
        "CycleCount": 10,
        "AppleRawMaxCapacity": 5500,
        "DesignCapacity": 5000
    }
    score = compute_health_score(data, scan_score=40)  # zero entropy penalty
    assert score <= 60

def test_high_cycles_deduct_score():
    data = {
        "CycleCount": 1500,
        "AppleRawMaxCapacity": 4000,
        "DesignCapacity": 5000
    }
    score = compute_health_score(data, scan_score=0)
    assert score < 100

def test_low_capacity_deducts_score():
    data = {
        "CycleCount": 50, 
        "AppleRawMaxCapacity": 2500, 
        "DesignCapacity": 5000
    }
    score = compute_health_score(data, scan_score=0)
    assert score < 100

# --- Trends Tests ---

def test_trend_up_when_cycles_increase():
    current_data = {"CycleCount": 10}
    last_entry = {"parsed": {"CycleCount": 5}}
    trends = compute_trends(current_data, last_entry)
    assert trends.get("cycles") == "up"

def test_trend_stable_for_op_time_recent():
    current_data = {"TotalOperatingTime": 1000}
    last_entry = {
        "parsed": {"TotalOperatingTime": 1000}, 
        "timestamp": datetime.now().isoformat()
    }
    trends = compute_trends(current_data, last_entry)
    assert trends.get("op_time") == "stable"
