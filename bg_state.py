"""Battery Guardian — shared mutable scan state.

All modules that need to read or write scan state import from here.
Python's module cache guarantees every importer shares the same objects.
Never rebind `state` from outside this module — only mutate via state["key"] = value.
"""

import threading

state_lock = threading.Lock()
stop_scan = threading.Event()

state = {
    "status": "idle",
    "progress": 0,
    "log": [],
    "verdict": "READY",
    "score": 0,
    "health_score": 0,
    "scan_mode": "full",
    "mac_model": "--",
    "trends": {},
    "metrics": {
        "cycle_count": "--",
        "write_count": "--",
        "qmax_var": "--",
        "op_time": "--",
        "op_time_raw": 0,
        "health": "--",
        "ratio": "--",
        "serial": "--",
        "temperature": "--",
        "manufacture_date": "--",
    },
}
