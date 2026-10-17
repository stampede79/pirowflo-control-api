import os
import subprocess
import socket

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(
    title="PiRowFlo Control API",
    version="0.1.0"
)

SUPERVISORCTL = os.environ.get(
    "PIROWFLO_SUPERVISORCTL",
    "/opt/pirowflo/venv/bin/supervisorctl",
)

SUPERVISOR_CONFIG = os.environ.get(
    "PIROWFLO_SUPERVISOR_CONFIG",
    "/opt/pirowflo/services/supervisord.conf",
)

CONTROL_SOCKET = os.environ.get(
    "PIROWFLO_CONTROL_SOCKET",
    "/tmp/pirowflo-control.sock",
)

PROFILES = {
    "combined": "pirowflo_SR_SmartRow_Bluetooth_AntPlus",
    "bluetooth": "pirowflo_SR_Smartrow_Bluetooth_only",
    "ant": "pirowflo_SR_Smartrow_AntPlus_only",
}

API_KEY = os.environ.get("PIROWFLO_API_KEY")

if not API_KEY:
    raise RuntimeError("PIROWFLO_API_KEY is not configured")


def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

def get_smartrow_status():
    smartrow_device = "dev_E8_F6_A2_1E_C4_69"

    try:
        result = subprocess.run(
            ["busctl", "tree", "org.bluez"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        device_path = None

        for line in result.stdout.splitlines():
            if smartrow_device.lower() in line.lower():
                start = line.find("/org/bluez/")
                if start != -1:
                    path = line[start:].strip()

                    # Nur das Device selbst, nicht die GATT-Unterobjekte
                    if path.endswith(smartrow_device):
                        device_path = path
                        break

        if device_path is None:
            return {
                "available": False,
                "connected": False,
                "services_resolved": False,
                "adapter": None,
            }

        def get_bool_property(property_name):
            result = subprocess.run(
                [
                    "busctl",
                    "get-property",
                    "org.bluez",
                    device_path,
                    "org.bluez.Device1",
                    property_name,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            return (
                result.returncode == 0
                and result.stdout.strip() == "b true"
            )

        connected = get_bool_property("Connected")
        services_resolved = get_bool_property("ServicesResolved")

        parts = device_path.split("/")
        adapter = parts[3] if len(parts) > 3 else None

        return {
            "available": True,
            "connected": connected,
            "services_resolved": services_resolved,
            "adapter": adapter,
        }

    except Exception:
        return {
            "available": False,
            "connected": False,
            "services_resolved": False,
            "adapter": None,
        }

def supervisor_status():
    result = subprocess.run(
        [
            SUPERVISORCTL,
            "-c",
            SUPERVISOR_CONFIG,
            "status",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    return result.stdout


@app.get("/")
def root():
    return {
        "service": "PiRowFlo Control API",
        "status": "ok",
    }


@app.get("/api/status")
def status(x_api_key: str = Header(...)):
    require_api_key(x_api_key)
    output = supervisor_status()

    profiles = {}

    for mode, process_name in PROFILES.items():
        line = next(
            (
                line
                for line in output.splitlines()
                if line.startswith(process_name)
            ),
            None,
        )

        if line is None:
            state = "UNKNOWN"
        else:
            parts = line.split()
            state = parts[1] if len(parts) > 1 else "UNKNOWN"

        profiles[mode] = {
            "process": process_name,
            "state": state,
        }

    return {
        "profiles": profiles,
        "smartrow": get_smartrow_status(),
    }

def supervisor_command(command, process_name):
    result = subprocess.run(
        [
            SUPERVISORCTL,
            "-c",
            SUPERVISOR_CONFIG,
            command,
            process_name,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def stop_all():
    results = {}

    for mode, process_name in PROFILES.items():
        results[mode] = supervisor_command("stop", process_name)

    return results


def start_mode(mode):
    if mode not in PROFILES:
        return None

    # Ensure only one PiRowFlo profile can run at a time.
    stop_all()

    result = supervisor_command(
        "start",
        PROFILES[mode],
    )

    return result

@app.post("/api/start/{mode}")
def start(mode: str, x_api_key: str = Header(...)):
    require_api_key(x_api_key)
    if mode not in PROFILES:
        return {
            "success": False,
            "error": "Unknown mode",
            "valid_modes": list(PROFILES.keys()),
        }

    result = start_mode(mode)

    return {
        "success": result["returncode"] == 0,
        "mode": mode,
        "result": result,
    }


@app.post("/api/stop")
def stop(x_api_key: str = Header(...)):
    require_api_key(x_api_key)
    results = stop_all()

    return {
        "success": True,
        "results": results,
    }


@app.post("/api/restart")
def restart(x_api_key: str = Header(...)):
    require_api_key(x_api_key)
    output = supervisor_status()

    active_mode = None

    for mode, process_name in PROFILES.items():
        for line in output.splitlines():
            if line.startswith(process_name):
                parts = line.split()

                if len(parts) > 1 and parts[1] == "RUNNING":
                    active_mode = mode
                    break

    if active_mode is None:
        return {
            "success": False,
            "error": "No PiRowFlo profile is currently running",
        }

    result = supervisor_command(
        "restart",
        PROFILES[active_mode],
    )

    return {
        "success": result["returncode"] == 0,
        "mode": active_mode,
        "result": result,
    }

@app.post("/api/reset")
def reset_smartrow(x_api_key: str = Header(...)):
    require_api_key(x_api_key)

    smartrow = get_smartrow_status()

    if not smartrow["connected"] or not smartrow["services_resolved"]:
        raise HTTPException(
            status_code=409,
            detail="SmartRow is not connected and ready",
        )

    if not os.path.exists(CONTROL_SOCKET):
        raise HTTPException(
            status_code=503,
            detail="PiRowFlo control socket is not available",
        )

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(CONTROL_SOCKET)
            sock.sendall(b"reset")
            response = sock.recv(1024).decode().strip()

        if response != "OK":
            raise HTTPException(
                status_code=500,
                detail=f"PiRowFlo reset failed: {response}",
            )

        return {
            "success": True,
            "message": "SmartRow reset requested",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not communicate with PiRowFlo: {e}",
        )
