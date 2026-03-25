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
    """Get the Mac model name and chip."""
    try:
        res = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10
        )
        model_name = ""
        chip = ""
        for line in res.stdout.splitlines():
            line = line.strip()
            if "Model Name:" in line:
                model_name = line.split(":", 1)[1].strip()
            elif "Chip:" in line:
                chip = line.split(":", 1)[1].strip()
            elif "Processor Name:" in line and not chip:
                chip = line.split(":", 1)[1].strip()
        if model_name and chip:
            return f"{model_name} ({chip})"
        elif model_name:
            try:
                res2 = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=2
                )
                sysctl_chip = res2.stdout.strip()
                if sysctl_chip:
                    return f"{model_name} ({sysctl_chip})"
            except Exception:
                pass
            return model_name
        return "Mac"
    except Exception:
        return "Mac"
