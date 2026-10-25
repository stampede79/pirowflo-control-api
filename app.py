import json
import os
import subprocess
import socket

from fastapi import FastAPI, Header, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from pathlib import Path
from training_plan_apply import apply_training_plan

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

SMARTROW_ADAPTER_MAC = os.environ.get(
    "PIROWFLO_SMARTROW_ADAPTER_MAC",
    "00:1A:7D:DA:71:15",
).lower()

ANT_USB_VENDOR = "0fcf"

PROFILES = {
    "combined": "pirowflo_SR_SmartRow_Bluetooth_AntPlus",
    "bluetooth": "pirowflo_SR_Smartrow_Bluetooth_only",
    "ant": "pirowflo_SR_Smartrow_AntPlus_only",
}

API_KEY = os.environ.get("PIROWFLO_API_KEY")

if not API_KEY:
    raise RuntimeError("PIROWFLO_API_KEY is not configured")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not configured")

openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
)

TRAINING_PLAN_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)


def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

class TrainingPlanRequest(BaseModel):
    year: int = Field(ge=2026, le=2100)
    month: int = Field(ge=1, le=12)
    sessions_per_week: int = Field(ge=1, le=7)


class TrainingPlanWorkout(BaseModel):
    date: str
    name: str
    description: str
    warmup: str | None = None
    repeat: int = Field(default=1, ge=1, le=20)
    work: str
    recovery: str | None = None
    cooldown: str | None = None


class TrainingPlan(BaseModel):
    year: int
    month: int
    workouts: list[TrainingPlanWorkout]

def get_smartrow_adapter_status():
    result = {
        "available": False,
        "adapter": None,
        "powered": False,
        "soft_blocked": False,
        "hard_blocked": False,
    }

    try:
        tree = subprocess.run(
            ["busctl", "tree", "org.bluez"],
            capture_output=True,
            text=True,
            timeout=3,
        )

        adapters = set()

        for line in tree.stdout.splitlines():
            start = line.find("/org/bluez/hci")

            if start == -1:
                continue

            path = line[start:].strip()
            parts = path.split("/")

            if len(parts) >= 4:
                adapters.add(parts[3])

        for adapter in adapters:
            adapter_path = f"/org/bluez/{adapter}"

            address_result = subprocess.run(
                [
                    "busctl",
                    "get-property",
                    "org.bluez",
                    adapter_path,
                    "org.bluez.Adapter1",
                    "Address",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if address_result.returncode != 0:
                continue

            address = (
                address_result.stdout
                .strip()
                .removeprefix('s "')
                .removesuffix('"')
                .lower()
            )

            if address != SMARTROW_ADAPTER_MAC:
                continue

            result["available"] = True
            result["adapter"] = adapter

            powered_result = subprocess.run(
                [
                    "busctl",
                    "get-property",
                    "org.bluez",
                    adapter_path,
                    "org.bluez.Adapter1",
                    "Powered",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )

            result["powered"] = (
                powered_result.returncode == 0
                and powered_result.stdout.strip() == "b true"
            )

            rfkill_path = os.path.join(
                "/sys/class/bluetooth",
                adapter,
            )

            try:
                entries = os.listdir(rfkill_path)

                rfkill_entry = next(
                    (
                        entry
                        for entry in entries
                        if entry.startswith("rfkill")
                    ),
                    None,
                )

                if rfkill_entry:
                    base = os.path.join(
                        rfkill_path,
                        rfkill_entry,
                    )

                    with open(os.path.join(base, "soft")) as f:
                        result["soft_blocked"] = (
                            f.read().strip() == "1"
                        )

                    with open(os.path.join(base, "hard")) as f:
                        result["hard_blocked"] = (
                            f.read().strip() == "1"
                        )

            except OSError:
                pass

            return result

    except Exception:
        pass

    return result

def get_ant_status():
    result = {
        "available": False,
    }

    try:
        usb_root = "/sys/bus/usb/devices"

        supported_products = {
            "1008",  # ANTUSB2 / Suunto
            "1009",  # Garmin
            "1004",  # Older ANT stick
        }

        for entry in os.listdir(usb_root):
            device_path = os.path.join(usb_root, entry)

            vendor_file = os.path.join(device_path, "idVendor")
            product_file = os.path.join(device_path, "idProduct")

            if not os.path.isfile(vendor_file):
                continue

            if not os.path.isfile(product_file):
                continue

            try:
                with open(vendor_file) as f:
                    vendor = f.read().strip().lower()

                with open(product_file) as f:
                    product = f.read().strip().lower()

            except OSError:
                continue

            if vendor == ANT_USB_VENDOR and product in supported_products:
                result["available"] = True
                return result

    except Exception:
        pass

    return result

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

def get_live_metrics():
    if not os.path.exists(CONTROL_SOCKET):
        raise HTTPException(
            status_code=503,
            detail="PiRowFlo control socket is not available",
        )

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(CONTROL_SOCKET)
            sock.sendall(b"metrics")
            response = sock.recv(4096).decode().strip()

        if not response:
            raise HTTPException(
                status_code=503,
                detail="PiRowFlo returned no metrics",
            )

        return json.loads(response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not read PiRowFlo metrics: {e}",
        )


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
        "hardware": {
            "smartrow_bluetooth": get_smartrow_adapter_status(),
            "ant": get_ant_status(),
        },
    }

@app.get("/api/training-plan/draft")
def get_training_plan_draft(
    x_api_key: str = Header(...),
):
    require_api_key(x_api_key)

    if not TRAINING_PLAN_DIR.exists():
        return {
            "available": False,
            "draft": None,
        }

    drafts = sorted(
        TRAINING_PLAN_DIR.glob("????-??.json"),
        reverse=True,
    )

    if not drafts:
        return {
            "available": False,
            "draft": None,
        }

    draft_file = drafts[0]

    try:
        draft = json.loads(
            draft_file.read_text(
                encoding="utf-8",
            )
        )

        if draft.get("status") != "draft":
            return {
                "available": False,
                "draft": None,
            }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Training plan draft could not "
                f"be read: {exc}"
            ),
        ) from exc

    return {
        "available": True,
        "draft": draft,
    }

@app.post("/api/training-plan/draft/apply")
def apply_training_plan_draft(
    x_api_key: str = Header(...),
):
    require_api_key(x_api_key)

    draft_dir = Path(
        "/var/lib/pirowflo-control/training-plans"
    )

    drafts = sorted(
        draft_dir.glob("????-??.json"),
        reverse=True,
    )

    if not drafts:
        raise HTTPException(
            status_code=404,
            detail="No training plan draft available",
        )

    draft_file = drafts[0]

    try:
        draft = json.loads(
            draft_file.read_text(
                encoding="utf-8",
            )
        )

        target_month = draft.get("target_month")

        if not target_month:
            raise RuntimeError(
                "Draft has no target_month"
            )

        result = apply_training_plan(
            target_month
        )

        return {
            "success": True,
            "target_month": target_month,
            "status": result["status"],
            "applied_at": result.get(
                "applied_at"
            ),
            "created_events": len(
                result.get(
                    "applied_event_uids",
                    [],
                )
            ),
        }

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Training plan could not be "
                f"applied: {exc}"
            ),
        ) from exc

@app.get("/api/metrics")
def metrics(x_api_key: str = Header(...)):
    require_api_key(x_api_key)

    raw = get_live_metrics()

    smartrow = get_smartrow_status()

    stroke_rate_raw = float(raw.get("stroke_rate", 0) or 0)

    return {
        "smartrow_connected": smartrow["connected"],
        "smartrow_ready": (
            smartrow["connected"]
            and smartrow["services_resolved"]
        ),
        "rowing": (
            float(raw.get("watts", 0) or 0) > 0
            or float(raw.get("instantaneous pace", 0) or 0) > 0
        ),
        "power_w": int(raw.get("watts", 0) or 0),
        "stroke_rate_spm": stroke_rate_raw / 2,
        "pace_500m_seconds": int(
            raw.get("instantaneous pace", 0) or 0
        ),
        "distance_m": int(raw.get("total_distance_m", 0) or 0),
        "elapsed_seconds": int(raw.get("elapsedtime", 0) or 0),
        "heart_rate_bpm": int(raw.get("heart_rate", 0) or 0),
        "power_avg_w": float(raw.get("watts_avg", 0) or 0),
        "pace_avg_500m_seconds": int(raw.get("pace_avg", 0) or 0),
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

@app.post("/api/training-plan/generate")
def generate_training_plan(
    request: TrainingPlanRequest,
    x_api_key: str = Header(...),
):
    require_api_key(x_api_key)

    try:
        response = openai_client.responses.parse(
            model="gpt-6-luna",
            input=[
                {
                    "role": "system",
                    "content": (
                        "Du erstellst Trainingspläne für Indoor-Rudern. "
                        "Erstelle einen ausgewogenen Monatsplan. "
                        "Die Trainingseinheiten werden als Ganztagstermine "
                        "verwendet. Verwende ausschließlich Watt und SPM "
                        "als Trainingsziele. "
                        "warmup, work, recovery und cooldown müssen das "
                        "PiRowFlo-Format verwenden, zum Beispiel "
                        "'5m,80-90w' oder '40m,105-115w,16-18spm'. "
                        "Plane Erholungstage zwischen intensiven Einheiten."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Erstelle einen Trainingsplan für "
                        f"{request.month:02d}/{request.year} mit "
                        f"{request.sessions_per_week} Einheiten pro Woche."
                    ),
                },
            ],
            text_format=TrainingPlan,
        )

        plan = response.output_parsed

        if plan is None:
            raise RuntimeError(
                "OpenAI returned no structured training plan"
            )

        return plan

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Training plan generation failed: {exc}",
        ) from exc


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
