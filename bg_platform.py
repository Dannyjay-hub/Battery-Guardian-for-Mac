"""Battery Guardian — platform guard and Mac model detection."""

import platform
import subprocess


def check_platform():
    """Returns (ok, error_msg). Blocks Windows/Linux and battery-less Macs."""
    if platform.system() != "Darwin":
        return False, "NOT_MAC"
    try:
        res = subprocess.run(
            ["ioreg", "-l", "-w0", "-r", "-c", "AppleSmartBattery"],
            capture_output=True, text=True, timeout=10
        )
        if not res.stdout or "AppleSmartBattery" not in res.stdout:
            return False, "NO_BATTERY"
    except Exception:
        return False, "NO_BATTERY"
    return True, None


def get_mac_model():
    """Get the official Mac marketing name and chip (e.g. 'MacBook Air (M1, 2020)')."""
    try:
        import os
        plist_path = os.path.expanduser("~/Library/Preferences/com.apple.SystemProfiler.plist")
        res = subprocess.run(
            ["defaults", "read", plist_path, "CPU Names"],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "=" in line:
                    return line.split("=", 1)[1].strip(' ";')
    except Exception:
        pass

    # Fallback to system_profiler SPHardwareDataType if the plist is unavailable
    try:
        res = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10
        )
        model_name = ""
        for line in res.stdout.splitlines():
            line = line.strip()
            if "Model Name:" in line:
                model_name = line.split(":", 1)[1].strip()
        
        return model_name if model_name else "Mac"
    except Exception:
        return "Mac"
