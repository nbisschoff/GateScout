"""
GateScout — Eve Online situational awareness overlay.
Run with: python main.py
"""

import sys
import os
import threading


def _resource(relative: str) -> str:
    """Resolve path to a bundled asset — works both in dev and as a PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, relative)

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QIcon

from auth.eve_sso import login, get_access_token, get_saved_character
from api.location import get_current_system
from api.universe import get_neighbour_ids, get_kills_and_jumps, get_names_bulk, get_security_statuses
from ui.overlay import Overlay
from ui.detail_window import DetailWindow
from config import LOCATION_POLL_INTERVAL, KILLS_POLL_INTERVAL


class DataWorker(QObject):
    """Runs ESI polling on a background thread and emits signals to the UI."""
    location_changed = pyqtSignal(str, int)        # system_name, system_id
    neighbours_updated = pyqtSignal(list)           # list of row dicts
    current_kills_updated = pyqtSignal(int)         # ship kills in current system
    alert_triggered = pyqtSignal()                  # new kill detected in neighbour
    status_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, character_id: int):
        super().__init__()
        self._character_id = character_id
        self._running = False
        self._current_system_id = None
        self._neighbour_ids: list[int] = []
        self._neighbour_security: dict[int, float] = {}
        self._prev_kills: dict[int, int] = {}

    def start(self):
        self._running = True
        threading.Thread(target=self._location_loop, daemon=True).start()
        threading.Thread(target=self._kills_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _location_loop(self):
        import time
        while self._running:
            try:
                token = get_access_token()
                system_id = get_current_system(self._character_id, token)
                if system_id != self._current_system_id:
                    self._current_system_id = system_id
                    self._prev_kills.clear()
                    name = _safe_system_name(system_id)
                    self.location_changed.emit(name, system_id)
                    self._neighbour_ids = get_neighbour_ids(system_id)
                    self._neighbour_security = get_security_statuses(self._neighbour_ids)
                    self._fetch_and_emit_kills()
            except Exception as e:
                self.error_occurred.emit(str(e))
            time.sleep(LOCATION_POLL_INTERVAL)

    def _kills_loop(self):
        import time
        time.sleep(KILLS_POLL_INTERVAL)
        while self._running:
            try:
                self._fetch_and_emit_kills()
            except Exception as e:
                self.error_occurred.emit(str(e))
            time.sleep(KILLS_POLL_INTERVAL)

    def _fetch_and_emit_kills(self):
        if not self._neighbour_ids or not self._current_system_id:
            return
        import datetime
        self.status_updated.emit("refreshing...")
        all_ids = self._neighbour_ids + [self._current_system_id]
        stats = get_kills_and_jumps(all_ids)
        names = get_names_bulk(self._neighbour_ids)
        rows = [
            {
                "name": names.get(sid, str(sid)),
                "system_id": sid,
                "ship_kills": stats[sid]["ship_kills"],
                "jumps": stats[sid]["jumps"],
                "security": self._neighbour_security.get(sid, 0.0),
            }
            for sid in self._neighbour_ids
        ]

        # Sound alert if any neighbour has more kills than last check
        for sid in self._neighbour_ids:
            new_k = stats[sid]["ship_kills"]
            if new_k > self._prev_kills.get(sid, 0):
                self.alert_triggered.emit()
                break
        self._prev_kills = {sid: stats[sid]["ship_kills"] for sid in self._neighbour_ids}

        self.neighbours_updated.emit(rows)
        current_kills = stats.get(self._current_system_id, {}).get("ship_kills", 0)
        self.current_kills_updated.emit(current_kills)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.status_updated.emit(f"updated {now}")


def _check_for_update(overlay):
    """Background thread: compares current version against latest GitHub release."""
    import threading
    def _run():
        try:
            import requests
            from version import VERSION
            r = requests.get(
                "https://api.github.com/repos/nbisschoff/GateScout/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=8,
            )
            if not r.ok:
                return
            tag = r.json().get("tag_name", "").lstrip("v")
            if not tag:
                return
            current = tuple(int(x) for x in VERSION.split("."))
            latest  = tuple(int(x) for x in tag.split("."))
            if latest > current:
                overlay.show_update_available(tag)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _safe_system_name(system_id: int) -> str:
    try:
        names = get_names_bulk([system_id])
        return names.get(system_id, str(system_id))
    except Exception:
        return str(system_id)


class GateScout:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(True)
        icon_path = _resource(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_path):
            self._app.setWindowIcon(QIcon(icon_path))
        self._worker: DataWorker | None = None
        self._detail_window: DetailWindow | None = None
        self._overlay = Overlay(
            on_login=self._do_login,
            on_logout=self._do_logout,
        )
        self._overlay.system_clicked.connect(self._open_detail)

    def run(self):
        self._overlay.show()
        _check_for_update(self._overlay)

        # Auto-login if we have saved tokens
        char_id, char_name = get_saved_character()
        if char_id:
            self._start_worker(char_id, char_name)

        sys.exit(self._app.exec())

    def _do_login(self):
        try:
            char_id, char_name = login()
            self._start_worker(char_id, char_name)
        except Exception as e:
            QMessageBox.critical(self._overlay, "Login failed", str(e))

    def _do_logout(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
        from config import TOKEN_FILE
        try:
            os.remove(TOKEN_FILE)
        except FileNotFoundError:
            pass
        self._overlay.set_logged_out()

    def _play_alert(self):
        if not self._overlay.is_muted():
            from settings_manager import play_sound
            play_sound(self._overlay.get_sound(), self._overlay.get_volume())

    def _open_detail(self, system_name: str, system_id: int, _kills: int):
        if self._detail_window:
            self._detail_window.close()
        self._detail_window = DetailWindow(
            system_name, system_id, self._overlay.pos()
        )
        self._detail_window.show()

    def _start_worker(self, char_id: int, char_name: str):
        if self._worker:
            self._worker.stop()
        self._overlay.set_logged_in(char_name)
        self._overlay.set_current_system("Locating...")
        self._worker = DataWorker(char_id)
        self._worker.location_changed.connect(
            lambda name, sid: self._overlay.set_current_system(name, sid)
        )
        self._worker.neighbours_updated.connect(self._overlay.update_neighbours)
        self._worker.current_kills_updated.connect(self._overlay.set_current_kills)
        self._worker.alert_triggered.connect(self._play_alert)
        self._worker.status_updated.connect(self._overlay.set_status)
        self._worker.error_occurred.connect(
            lambda msg: self._overlay.set_status(f"err: {msg[:40]}")
        )
        self._worker.start()


if __name__ == "__main__":
    GateScout().run()
