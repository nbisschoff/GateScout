import os
import sys
import json

_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "GateScout", "settings.json"
)

_DEFAULTS = {
    "opacity": 0.90,
    "sound":   "Alert 1",
    "volume":  0.80,
}

SOUNDS = {
    "Alert 1": "assets/01.mp3",
    "Alert 2": "assets/02.mp3",
    "Alert 3": "assets/03.mp3",
    "Alert 4": "assets/04.mp3",
    "Alert 5": "assets/05.mp3",
    "Alert 6": "assets/06.mp3",
}

_pygame_ready = False


def _init_pygame():
    global _pygame_ready
    if not _pygame_ready:
        try:
            import pygame
            pygame.mixer.init()
            _pygame_ready = True
        except Exception:
            pass


def _resolve(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


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


def play_sound(name: str, volume: float = 0.80):
    import threading
    def _run():
        try:
            _init_pygame()
            if not _pygame_ready:
                return
            import pygame
            path = _resolve(SOUNDS.get(name, "assets/01.mp3"))
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
            pygame.mixer.music.play()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
