import os
import json

_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "GateScout", "settings.json"
)

_DEFAULTS = {
    "opacity": 0.90,
    "sound":   "double",
}

# Each sound is a list of (frequency_hz, duration_ms) beeps played in sequence
SOUNDS = {
    "Single beep":   [(880, 220)],
    "Double beep":   [(880, 130), (880, 180)],
    "Rising tone":   [(600, 150), (880, 220)],
    "Falling tone":  [(1000, 150), (660, 220)],
    "Triple beep":   [(880, 90), (880, 90), (880, 160)],
    "Alarm":         [(1100, 70), (800, 70), (1100, 70), (800, 120)],
}


def load() -> dict:
    try:
        with open(_FILE) as f:
            return {**_DEFAULTS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def save(data: dict):
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w") as f:
        json.dump(data, f, indent=2)


def play_sound(name: str):
    """Play the sound pattern for the given name. Safe to call from any thread."""
    import threading
    pattern = SOUNDS.get(name, SOUNDS["Double beep"])
    def _run():
        import time
        try:
            import winsound
            for freq, dur in pattern:
                winsound.Beep(freq, dur)
                time.sleep(0.04)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
