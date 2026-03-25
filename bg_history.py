"""Battery Guardian — scan history manager."""

import json
import os
import logging
from datetime import datetime

from bg_config import HISTORY_FILE, MAX_HISTORY

logger = logging.getLogger("battery_guardian")


class HistoryManager:
    FILE_PATH = HISTORY_FILE

    @staticmethod
    def load():
        if os.path.exists(HistoryManager.FILE_PATH):
            try:
                with open(HistoryManager.FILE_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @staticmethod
    def save_scan(raw_text, parsed_data, health_score):
        history = HistoryManager.load()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "serial": parsed_data.get("Serial", "Unknown"),
            "cycle_count": parsed_data.get("CycleCount", 0),
            "health_score": health_score,
            "parsed": parsed_data,
            "raw_text_snippet": raw_text[:2000],
        }
        history.append(entry)
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        try:
            tmp_path = HistoryManager.FILE_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(history, f, indent=2)
            os.replace(tmp_path, HistoryManager.FILE_PATH)
        except Exception as e:
            logger.warning(f"Save error: {e}")

    @staticmethod
    def get_last_scan():
        history = HistoryManager.load()
        if len(history) >= 1:
            return history[-1]
        return None

    @staticmethod
    def export_to_desktop():
        try:
            desktop = os.path.expanduser("~/Desktop")
            export_path = os.path.join(desktop, "battery_guardian_export.json")
            history = HistoryManager.load()
            with open(export_path, "w") as f:
                json.dump(history, f, indent=2)
            return True, export_path
        except Exception as e:
            return False, str(e)
