"""
Always-on-top transparent overlay window.
Drag it anywhere on screen. Double-click the title bar to collapse/expand.
"""

import os
import sys
import webbrowser

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QSizeGrip,
    QSystemTrayIcon, QMenu, QMessageBox, QApplication, QScrollArea,
)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QIcon, QAction


DARK_BG = "rgba(15, 15, 20, 210)"
HEADER_BG = "#1a1a2e"
ROW_BG = "#0f0f14"
ROW_ALT = "#131320"
BORDER = "#2a2a4a"
TEXT = "#c8c8d8"
ACCENT = "#4fc3f7"

KILL_COLORS = {
    0: "#4caf50",   # green — clear
    1: "#ffc107",   # amber — caution
    2: "#ff9800",   # orange — warning
}
KILL_HIGH = "#f44336"   # red — 3+


def _kill_color(n: int) -> str:
    return KILL_COLORS.get(n, KILL_HIGH)


def _sec_color(sec: float) -> str:
    if sec >= 0.5:
        return "#4caf50"
    elif sec >= 0.1:
        return "#ffc107"
    return "#f44336"


class _ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class Overlay(QMainWindow):
    system_clicked  = pyqtSignal(str, int, int)   # system_name, system_id, kills
    _update_ready   = pyqtSignal(str)             # emitted from bg thread, handled on main thread

    def __init__(self, on_login, on_logout):
        super().__init__()
        self._on_login = on_login
        self._on_logout = on_logout
        self._drag_pos = QPoint()
        self._collapsed = False
        self._current_system_name = ""
        self._current_system_id = None
        self._current_kills_count = 0
        self._help_window     = None
        self._muted           = False
        self._about_window    = None
        self._settings_window = None
        self._logged_in_name  = ""
        self._quit_confirmed  = False

        import settings_manager
        self._settings = settings_manager.load()

        self.setWindowTitle("GateScout")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(340, 260)

        self._build_ui()
        self.setWindowOpacity(self._settings["opacity"])
        self._update_ready.connect(self.show_update_available)
        self._setup_tray()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet(f"""
            #root {{
                background: {DARK_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QLabel {{ color: {TEXT}; }}
            QPushButton {{
                background: transparent;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {BORDER}; }}
        """)
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── title bar ──────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(30)
        title_bar.setStyleSheet(f"background: {HEADER_BG}; border-radius: 8px 8px 0 0;")
        title_bar.mouseDoubleClickEvent = self._toggle_collapse

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 8, 0)

        self._title_label = QLabel("GateScout")
        self._title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()

        self._update_btn = QPushButton()
        self._update_btn.setStyleSheet(
            "QPushButton { border: none; color: #ffd700; font-size: 10px; padding: 0 4px; }"
            "QPushButton:hover { color: #ffe066; text-decoration: underline; }"
        )
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.hide()
        tb_layout.addWidget(self._update_btn)

        self._login_btn = QPushButton("Login")
        self._login_btn.clicked.connect(self._on_login)
        tb_layout.addWidget(self._login_btn)

        self._logout_btn = QPushButton("Logout")
        self._logout_btn.clicked.connect(self._confirm_logout)
        self._logout_btn.hide()
        tb_layout.addWidget(self._logout_btn)

        _icon_style = "QPushButton {{ border: none; color: {c}; font-size: 12px; padding: 0; }} QPushButton:hover {{ color: {h}; }}"

        self._mute_btn = QPushButton("♪")
        self._mute_btn.setFixedSize(20, 20)
        self._mute_btn.setStyleSheet(_icon_style.format(c="#666", h="#4fc3f7"))
        self._mute_btn.setToolTip("Mute / unmute sound alerts")
        self._mute_btn.clicked.connect(self._toggle_mute)
        tb_layout.addWidget(self._mute_btn)

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(20, 20)
        settings_btn.setStyleSheet(_icon_style.format(c="#666", h="#4fc3f7"))
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self._show_settings)
        tb_layout.addWidget(settings_btn)

        info_btn = QPushButton("ⓘ")
        info_btn.setFixedSize(20, 20)
        info_btn.setStyleSheet(_icon_style.format(c="#666", h="#4fc3f7"))
        info_btn.setToolTip("About GateScout")
        info_btn.clicked.connect(self._show_about)
        tb_layout.addWidget(info_btn)

        help_btn = QPushButton("?")
        help_btn.setFixedSize(20, 20)
        help_btn.setStyleSheet(_icon_style.format(c="#666", h="#4fc3f7"))
        help_btn.clicked.connect(self._show_help)
        tb_layout.addWidget(help_btn)

        reset_btn = QPushButton("↺")
        reset_btn.setFixedSize(20, 20)
        reset_btn.setStyleSheet(_icon_style.format(c="#666", h="#4fc3f7"))
        reset_btn.setToolTip("Reset to default size")
        reset_btn.clicked.connect(self._reset_size)
        tb_layout.addWidget(reset_btn)

        min_btn = QPushButton("─")
        min_btn.setFixedSize(20, 20)
        min_btn.setStyleSheet(_icon_style.format(c="#666", h="#4fc3f7"))
        min_btn.setToolTip("Minimise to system tray")
        min_btn.clicked.connect(self._minimise_to_tray)
        tb_layout.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(_icon_style.format(c="#666", h="#f44336"))
        close_btn.setToolTip("Quit GateScout")
        close_btn.clicked.connect(self._confirm_quit)
        tb_layout.addWidget(close_btn)

        outer.addWidget(title_bar)

        # ── collapsed summary strip ────────────────────────────────
        self._summary_strip = QWidget()
        self._summary_strip.setFixedHeight(22)
        self._summary_strip.setStyleSheet(
            f"background: {ROW_BG}; border-top: 1px solid {BORDER}; border-radius: 0 0 8px 8px;"
        )
        ss = QHBoxLayout(self._summary_strip)
        ss.setContentsMargins(10, 0, 10, 0)
        ss.setSpacing(6)

        self._sum_current = QLabel("◉ —")
        self._sum_current.setStyleSheet(f"color: {ACCENT}; font-size: 10px;")
        ss.addWidget(self._sum_current)

        _sep = QLabel("│")
        _sep.setStyleSheet(f"color: {BORDER}; font-size: 10px;")
        ss.addWidget(_sep)

        self._sum_neighbours = QLabel("—")
        self._sum_neighbours.setStyleSheet("color: #666; font-size: 10px;")
        ss.addStretch()
        ss.addWidget(self._sum_neighbours)

        self._summary_strip.hide()
        outer.addWidget(self._summary_strip)

        # ── body ───────────────────────────────────────────────────
        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(10, 8, 10, 10)
        body_layout.setSpacing(6)

        # current system row
        sys_row = QHBoxLayout()
        loc_icon = QLabel("◉")
        loc_icon.setStyleSheet(f"color: {ACCENT}; font-size: 13px;")
        self._current_label = _ClickableLabel("Not logged in")
        self._current_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._current_label.setStyleSheet(f"color: {ACCENT};")
        self._current_label.clicked.connect(self._on_current_system_clicked)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #666; font-size: 10px;")
        sys_row.addWidget(loc_icon)
        sys_row.addWidget(self._current_label)
        sys_row.addStretch()
        sys_row.addWidget(self._status_label)
        body_layout.addLayout(sys_row)

        # neighbour table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["", "System", "Sec", "Kills/hr", "Jumps/hr"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 24)
        self._table.setColumnWidth(2, 45)
        self._table.setColumnWidth(3, 65)
        self._table.setColumnWidth(4, 65)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {ROW_BG};
                border: 1px solid {BORDER};
                border-radius: 4px;
                gridline-color: {BORDER};
                color: {TEXT};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {HEADER_BG};
                color: #888;
                border: none;
                border-bottom: 1px solid {BORDER};
                padding: 4px;
                font-size: 11px;
            }}
            QTableWidget::item {{ padding: 3px 6px; }}
            QTableWidget::item:alternate {{ background: {ROW_ALT}; }}
        """)
        self._table.setAlternatingRowColors(True)
        self._table.cellClicked.connect(self._on_row_clicked)
        self._table.setCursor(Qt.CursorShape.PointingHandCursor)
        body_layout.addWidget(self._table)

        outer.addWidget(self._body)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        self._grip.setStyleSheet("QSizeGrip { background: transparent; }")
        self._grip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - self._grip.width() - 2,
                        self.height() - self._grip.height() - 2)
        self._grip.raise_()

    # ── public update methods ───────────────────────────────────────

    def show_update_available(self, version: str):
        import webbrowser
        self._update_btn.setText(f"↓ v{version} available")
        self._update_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/nbisschoff/GateScout/releases/latest")
        )
        self._update_btn.show()

    def set_current_system(self, name: str, system_id: int = None):
        self._current_system_name = name
        self._current_system_id = system_id
        self._current_kills_count = 0
        self._current_label.setText(name)
        self._current_label.setStyleSheet(f"color: {ACCENT};")
        f = self._current_label.font()
        f.setUnderline(False)
        self._current_label.setFont(f)
        self._current_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._refresh_summary_strip()

    def set_current_kills(self, kills: int):
        self._current_kills_count = kills
        name = getattr(self, "_current_system_name", "")
        suffix = f"  [{kills} kill{'s' if kills != 1 else ''}]" if kills > 0 else ""
        self._current_label.setText(name + suffix)
        color = _kill_color(kills) if kills > 0 else ACCENT
        self._current_label.setStyleSheet(f"color: {color};")
        f = self._current_label.font()
        f.setUnderline(kills > 0)
        self._current_label.setFont(f)
        self._current_label.setCursor(
            Qt.CursorShape.PointingHandCursor if kills > 0 else Qt.CursorShape.ArrowCursor
        )
        self._refresh_summary_strip()

    def set_status(self, text: str):
        self._status_label.setText(text)

    def set_logged_in(self, name: str):
        self._logged_in_name = name
        self._login_btn.hide()
        self._logout_btn.show()
        self._logout_btn.setText(f"↩ {name}")

    def set_logged_out(self):
        self._login_btn.show()
        self._logout_btn.hide()
        self._current_label.setText("Not logged in")
        self._current_label.setStyleSheet(f"color: {TEXT};")
        self.clear_table()

    def update_neighbours(self, rows: list[dict]):
        """
        rows: [{"name": str, "system_id": int, "ship_kills": int, "jumps": int}, ...]
        Sorted by kills descending so the dangerous systems float to the top.
        """
        rows = sorted(rows, key=lambda r: r["ship_kills"], reverse=True)
        self._row_data = rows   # keep for click lookup
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            kills     = row["ship_kills"]
            jumps     = row["jumps"]
            sec       = row.get("security", 0.0)
            has_kills = kills > 0
            system_id = row["system_id"]

            # col 0 — zKillboard link button
            zk_btn = QPushButton("zK")
            zk_btn.setFixedSize(20, 16)
            zk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            zk_btn.setToolTip(f"Open {row['name']} on zKillboard")
            zk_btn.setStyleSheet(
                "QPushButton { border: none; color: #446688; font-size: 8px; "
                "font-weight: bold; background: transparent; padding: 0; }"
                "QPushButton:hover { color: #4fc3f7; }"
            )
            zk_btn.clicked.connect(
                lambda _checked, sid=system_id:
                    webbrowser.open(f"https://zkillboard.com/system/{sid}/")
            )
            cell_wrap = QWidget()
            cell_wrap.setStyleSheet("background: transparent;")
            cl = QHBoxLayout(cell_wrap)
            cl.setContentsMargins(2, 0, 2, 0)
            cl.addWidget(zk_btn)
            self._table.setCellWidget(i, 0, cell_wrap)

            # col 1 — system name
            name_item  = QTableWidgetItem(row["name"])
            sec_item   = QTableWidgetItem(f"{sec:.1f}")
            kills_item = QTableWidgetItem(str(kills))
            jumps_item = QTableWidgetItem(f"{jumps:,}")

            sec_item.setForeground(QColor(_sec_color(sec)))

            color = QColor(_kill_color(kills))
            kills_item.setForeground(color)
            if kills >= 3:
                name_item.setForeground(color)

            if has_kills:
                f = name_item.font()
                f.setUnderline(True)
                name_item.setFont(f)
                name_item.setToolTip("Click to see kill details")

            for item in (name_item, sec_item, kills_item, jumps_item):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            self._table.setItem(i, 1, name_item)
            self._table.setItem(i, 2, sec_item)
            self._table.setItem(i, 3, kills_item)
            self._table.setItem(i, 4, jumps_item)

        # resize window to fit rows (min 180, max 420) — skip if collapsed
        if not self._collapsed:
            row_h = self._table.rowHeight(0) if rows else 24
            new_h = min(420, max(180, 110 + len(rows) * row_h))
            self.resize(340, new_h)
        self._refresh_summary_strip()

    def _on_current_system_clicked(self):
        if self._current_kills_count > 0 and self._current_system_id:
            self.system_clicked.emit(
                self._current_system_name,
                self._current_system_id,
                self._current_kills_count,
            )

    def _on_row_clicked(self, row_index: int, col: int):
        if col == 0:   # zK button column — handled by the button itself
            return
        if not hasattr(self, "_row_data") or row_index >= len(self._row_data):
            return
        row = self._row_data[row_index]
        if row["ship_kills"] > 0:
            self.system_clicked.emit(row["name"], row["system_id"], row["ship_kills"])

    def clear_table(self):
        self._table.setRowCount(0)

    # ── drag to move ───────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            near_grip = pos.x() > self.width() - 20 and pos.y() > self.height() - 20
            self._drag_pos = QPoint() if near_grip else (
                e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def is_muted(self) -> bool:
        return self._muted

    def _toggle_mute(self):
        self._muted = not self._muted
        if self._muted:
            self._mute_btn.setStyleSheet(
                "QPushButton { border: none; color: #f44336; font-size: 12px; "
                "padding: 0; text-decoration: line-through; }"
            )
        else:
            self._mute_btn.setStyleSheet(
                "QPushButton { border: none; color: #666; font-size: 12px; padding: 0; } "
                "QPushButton:hover { color: #4fc3f7; }"
            )

    def _reset_size(self):
        if self._collapsed:
            self.resize(340, 54)
            return
        rows = getattr(self, "_row_data", [])
        row_h = self._table.rowHeight(0) if rows else 24
        h = min(420, max(180, 110 + len(rows) * row_h)) if rows else 180
        self.resize(340, h)

    def _show_settings(self):
        if self._settings_window and self._settings_window.isVisible():
            self._settings_window.close()
            return
        from ui.settings_window import SettingsWindow
        self._settings_window = SettingsWindow(
            self.pos(),
            self._settings["opacity"],
            self._settings["sound"],
            self._settings.get("volume", 0.80),
        )
        self._settings_window.opacity_changed.connect(self._apply_opacity)
        self._settings_window.sound_changed.connect(self._apply_sound)
        self._settings_window.volume_changed.connect(self._apply_volume)
        self._settings_window.save_requested.connect(self._on_save_settings)
        self._settings_window.show()

    def _apply_opacity(self, value: float):
        self._settings["opacity"] = value
        self.setWindowOpacity(value)

    def _apply_sound(self, name: str):
        self._settings["sound"] = name

    def _apply_volume(self, value: float):
        self._settings["volume"] = value

    def _on_save_settings(self, opacity: float, sound: str, volume: float):
        self._settings["opacity"] = opacity
        self._settings["sound"]   = sound
        self._settings["volume"]  = volume
        self.setWindowOpacity(opacity)
        import settings_manager
        settings_manager.save(self._settings)

    def get_sound(self) -> str:
        return self._settings.get("sound", "Alert 1")

    def get_volume(self) -> float:
        return self._settings.get("volume", 0.80)

    def _show_about(self):
        if self._about_window and self._about_window.isVisible():
            self._about_window.close()
            return
        self._about_window = _AboutWindow(self.pos())
        self._about_window.show()

    def _show_help(self):
        if self._help_window and self._help_window.isVisible():
            self._help_window.close()
            return
        self._help_window = _HelpWindow(self.pos())
        self._help_window.show()

    def _setup_tray(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
        icon_path = os.path.join(base, "assets", "icon.ico")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("GateScout")

        menu = QMenu()
        restore_action = QAction("Restore GateScout", self)
        restore_action.triggered.connect(self._restore_from_tray)
        menu.addAction(restore_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._confirm_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _minimise_to_tray(self):
        self.hide()
        self._tray.showMessage(
            "GateScout",
            "Running in the background. Double-click to restore.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _confirm_quit(self):
        reply = QMessageBox.question(
            self,
            "Quit GateScout",
            "Are you sure you want to quit GateScout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._quit_confirmed = True
            QApplication.instance().quit()

    def _confirm_logout(self):
        name = self._logged_in_name or "your character"
        reply = QMessageBox.question(
            self,
            "Log Out",
            f"Log out as {name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._on_logout()

    def closeEvent(self, event):
        if self._quit_confirmed:
            event.accept()
        else:
            event.ignore()
            self._minimise_to_tray()

    def _refresh_summary_strip(self):
        if not self._collapsed:
            return
        name  = self._current_system_name or "Not logged in"
        kills = self._current_kills_count
        c_color = _kill_color(kills) if kills > 0 else ACCENT
        kill_str = f"· {kills} kill{'s' if kills != 1 else ''}" if kills > 0 else "· 0 kills"
        self._sum_current.setText(f"◉ {name}  {kill_str}")
        self._sum_current.setStyleSheet(f"color: {c_color}; font-size: 10px; background: transparent;")

        rows = getattr(self, "_row_data", [])
        if not rows:
            self._sum_neighbours.setText("no data")
            self._sum_neighbours.setStyleSheet("color: #666; font-size: 10px; background: transparent;")
            return
        total_n  = len(rows)
        total_k  = sum(r["ship_kills"] for r in rows)
        active   = sum(1 for r in rows if r["ship_kills"] > 0)
        n_color  = _kill_color(total_k) if total_k > 0 else "#4caf50"
        self._sum_neighbours.setText(
            f"{total_n} neighbours  ·  {total_k} kills  ·  {active} active"
        )
        self._sum_neighbours.setStyleSheet(f"color: {n_color}; font-size: 10px; background: transparent;")

    def _toggle_collapse(self, _event=None):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._summary_strip.setVisible(self._collapsed)
        if self._collapsed:
            self._refresh_summary_strip()
            self.resize(self.width(), 54)   # 30 title + 22 strip + 2 border
        else:
            rows = getattr(self, "_row_data", [])
            row_h = self._table.rowHeight(0) if rows else 24
            new_h = min(420, max(180, 110 + len(rows) * row_h))
            self.resize(self.width(), new_h)


class _AboutWindow(QWidget):
    def __init__(self, parent_pos: QPoint):
        super().__init__()
        self._drag_pos = QPoint()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()
        from ui.utils import smart_pos
        self.move(smart_pos(parent_pos, 340, self.width(), self.height(), prefer_left=True))

    def _build_ui(self):
        from version import VERSION
        root = QWidget(self)
        root.setObjectName("root")
        root.setStyleSheet("""
            #root {
                background: rgba(15, 15, 20, 225);
                border: 1px solid #2a2a4a;
                border-radius: 8px;
            }
            QLabel { color: #c8c8d8; }
            QPushButton { background: transparent; color: #666; border: none; font-size: 12px; padding: 0; }
            QPushButton:hover { color: #f44336; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background: #1a1a2e; border-radius: 8px 8px 0 0;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 8, 0)
        lbl = QLabel("GateScout — About")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #4fc3f7; background: transparent;")
        tb.addWidget(lbl)
        tb.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.clicked.connect(self.close)
        tb.addWidget(close_btn)
        layout.addWidget(title_bar)

        body = QLabel()
        body.setWordWrap(True)
        body.setContentsMargins(16, 12, 16, 16)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setOpenExternalLinks(True)
        body.setText(f"""
<style>
  b   {{ color: #4fc3f7; }}
  .d  {{ color: #888899; }}
  .gd {{ color: #ffd700; }}
  p   {{ margin: 4px 0; }}
  hr  {{ border: none; border-top: 1px solid #2a2a4a; margin: 8px 0; }}
</style>

<p style="font-size:18px; color:#4fc3f7;"><b>GateScout</b></p>
<p class="d">Version {VERSION}</p>

<hr/>

<p>Situational awareness for EVE Online.<br/>
Monitors kills and jump traffic in neighbouring systems<br/>
so you know what's waiting on the other side of the gate.</p>

<hr/>

<p><b>Created by</b><br/>
<span style="font-size:13px; color:#c8c8d8;">Draven Ezekiel</span></p>

<hr/>

<p><b>Support the Project</b><br/>
If GateScout has saved your ship — or your pod — consider<br/>
sending a donation in ISK to <b>Draven Ezekiel</b> in-game.<br/>
<span class="d">Right-click their name → Give Money</span></p>

<p class="d" style="font-size:10px;">Every ISK goes toward keeping the<br/>
server lights on and the gates scouted. o7</p>
""")
        layout.addWidget(body)
        self.adjustSize()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)


class _HelpWindow(QWidget):
    def __init__(self, parent_pos: QPoint):
        super().__init__()
        self._drag_pos = QPoint()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()

        # Size to available screen space, open full if it fits
        from ui.utils import smart_pos
        screen  = QApplication.primaryScreen().availableGeometry()
        ideal_w = 400
        ideal_h = 740
        # Probe position at ideal size to find available vertical room
        probe   = smart_pos(parent_pos, 340, ideal_w, ideal_h, prefer_left=True)
        avail_h = screen.bottom() - probe.y() - 10
        final_h = min(ideal_h, max(420, avail_h))
        # Recalculate position with the true final height
        pos = smart_pos(parent_pos, 340, ideal_w, final_h, prefer_left=True)
        self.resize(ideal_w, final_h)
        self.move(pos)

    def _build_ui(self):
        root = QWidget(self)
        root.setObjectName("root")
        root.setStyleSheet(f"""
            #root {{
                background: rgba(15, 15, 20, 225);
                border: 1px solid #2a2a4a;
                border-radius: 8px;
            }}
            QLabel {{ color: #c8c8d8; }}
            QPushButton {{ background: transparent; color: #666; border: none; font-size: 12px; padding: 0; }}
            QPushButton:hover {{ color: #f44336; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background: #1a1a2e; border-radius: 8px 8px 0 0;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 8, 0)
        lbl = QLabel("GateScout — How to Use")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #4fc3f7; background: transparent;")
        tb.addWidget(lbl)
        tb.addStretch()
        reset_btn = QPushButton("↺")
        reset_btn.setFixedSize(18, 18)
        reset_btn.setStyleSheet("QPushButton { border: none; color: #666; font-size: 11px; padding: 0; } QPushButton:hover { color: #4fc3f7; }")
        reset_btn.setToolTip("Reset to default size")
        reset_btn.clicked.connect(self._reset_default)
        tb.addWidget(reset_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.clicked.connect(self.close)
        tb.addWidget(close_btn)
        layout.addWidget(title_bar)

        body = QLabel()
        body.setWordWrap(True)
        body.setContentsMargins(14, 10, 14, 14)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setText("""
<style>
  b   { color: #4fc3f7; }
  .g  { color: #4caf50; }
  .y  { color: #ffc107; }
  .o  { color: #ff9800; }
  .r  { color: #f44336; }
  .d  { color: #888899; }
  .gd { color: #ffd700; }
  p   { margin: 3px 0; }
  hr  { border: none; border-top: 1px solid #2a2a4a; margin: 6px 0; }
</style>

<p><b>YOUR SYSTEM</b> — shown at top with ◉.<br/>
If ships were killed there in the last hour, the name turns
coloured and shows a kill count. <b>Click it</b> to open the
kill summary, same as clicking a neighbour.</p>

<hr/>

<p><b>NEIGHBOUR TABLE</b> — one row per system reachable in 1 jump.</p>
<p>&nbsp;&nbsp;<b>zK</b> — opens that system's page on zKillboard in your browser.</p>
<p>&nbsp;&nbsp;<b>System</b> — <u>Underlined</u> = kills detected.
Click to open the Kill List for that system.</p>
<p>&nbsp;&nbsp;<b>Sec</b> — Security status of the system:<br/>
&nbsp;&nbsp;&nbsp;&nbsp;<span class='g'>■ ≥ 0.5</span> high-sec &nbsp;
<span class='y'>■ 0.1–0.4</span> low-sec &nbsp;
<span class='r'>■ ≤ 0.0</span> null-sec / wormhole</p>
<p>&nbsp;&nbsp;<b>Kills/hr</b> — Ships + pods destroyed in the last hour.</p>
<p>&nbsp;&nbsp;<b>Jumps/hr</b> — Player jump traffic. High = busy gate.</p>

<hr/>

<p><b>KILL COLOURS</b> (applies to system name and kills count)</p>
<p>&nbsp;&nbsp;<span class='g'>■ Green</span> &nbsp;= 0 kills — looks clear</p>
<p>&nbsp;&nbsp;<span class='y'>■ Yellow</span> = 1–2 kills — exercise caution</p>
<p>&nbsp;&nbsp;<span class='o'>■ Orange</span> = 3–4 kills — hostile activity likely</p>
<p>&nbsp;&nbsp;<span class='r'>■ Red</span> &nbsp;&nbsp;= 5+ kills — danger, find an alternative</p>

<hr/>

<p><b>KILL LIST</b> — Opens when you click an underlined system
or your current system name. Shows every kill in the last hour:<br/>
&nbsp;&nbsp;<b>Ship</b> — what was destroyed (underlined, click for summary)<br/>
&nbsp;&nbsp;<b>Attacker</b> — corp [alliance] of the final blow<br/>
&nbsp;&nbsp;<b>When</b> — how long ago the kill happened<br/>
&nbsp;&nbsp;<span class='y'>Yellow location</span> = near a stargate (possible camp)<br/>
&nbsp;&nbsp;White location = deep space</p>

<hr/>

<p><b>KILL SUMMARY</b> — Opens when you click a ship in the Kill List.
Shows the full picture of that specific kill:<br/>
&nbsp;&nbsp;Ship render image + victim name, corp, alliance<br/>
&nbsp;&nbsp;<span class='gd'>■ ISK value</span> lost in the kill<br/>
&nbsp;&nbsp;<b>★ Final blow</b> — who landed the killing shot and damage done<br/>
&nbsp;&nbsp;Other attacking corps grouped by pilot count<br/>
&nbsp;&nbsp;<b>zK</b> button — opens the full kill on zKillboard in your browser</p>

<hr/>

<p><b>SOUND ALERT</b> — A beep plays automatically when new kills
appear in a neighbouring system between refreshes.<br/>
&nbsp;&nbsp;<b>♪</b> button in the title bar — mute / unmute.
Red strikethrough means muted.</p>

<hr/>

<p><b>DATA REFRESH</b><br/>
&nbsp;&nbsp;Location checks: every 5 seconds<br/>
&nbsp;&nbsp;Kills &amp; jumps: every 30 seconds<br/>
&nbsp;&nbsp;<span class='d'>Data may lag a few minutes behind the in-game map — this
is an EVE API limitation, not a bug.</span></p>

<hr/>

<p><b>WINDOW CONTROLS</b><br/>
&nbsp;&nbsp;<b>Drag</b> — click and drag anywhere to move a window<br/>
&nbsp;&nbsp;<b>Resize</b> — drag the bottom-right corner of any window<br/>
&nbsp;&nbsp;<b>↺</b> — reset window to its default size<br/>
&nbsp;&nbsp;<b>Double-click title bar</b> — collapse to a compact summary strip showing your current system kills and total neighbour activity; double-click again to expand<br/>
&nbsp;&nbsp;<b>─</b> — minimise to system tray; Alt+F4 also sends it to tray<br/>
&nbsp;&nbsp;<b>✕</b> — prompts to confirm, then quits GateScout completely<br/>
&nbsp;&nbsp;Double-click the tray icon, or right-click → Restore GateScout, to bring the overlay back</p>
""")
        body.setContentsMargins(14, 10, 14, 14)

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #0f0f14; width: 6px; border-radius: 3px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #2a2a4a; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #4fc3f7; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout.addWidget(scroll)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        self._grip.setStyleSheet("QSizeGrip { background: transparent; }")
        self._grip.raise_()

    def _reset_default(self):
        screen  = QApplication.primaryScreen().availableGeometry()
        avail_h = screen.bottom() - self.y() - 10
        self.resize(400, min(740, max(420, avail_h)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - self._grip.width() - 2,
                        self.height() - self._grip.height() - 2)
        self._grip.raise_()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            near_grip = pos.x() > self.width() - 20 and pos.y() > self.height() - 20
            self._drag_pos = QPoint() if near_grip else (
                e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(e.globalPosition().toPoint() - self._drag_pos)
