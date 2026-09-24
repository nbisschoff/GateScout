"""
Kill summary popup — shows ship image, victim info, ISK value, and attacker breakdown.
Opened when clicking a row in the detail window.
"""

import threading
import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QSizeGrip, QFrame,
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QPixmap, QMouseEvent

DARK_BG   = "rgba(15, 15, 20, 225)"
HEADER_BG = "#1a1a2e"
ROW_BG    = "#0f0f14"
ROW_ALT   = "#131320"
BORDER    = "#2a2a4a"
TEXT      = "#c8c8d8"
ACCENT    = "#4fc3f7"
DIM       = "#555577"
GOLD      = "#ffd700"


def _icon_btn(text: str, hover: str = "#4fc3f7") -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(20, 20)
    btn.setStyleSheet(
        f"QPushButton {{ border: none; color: #666; font-size: 12px; padding: 0; }}"
        f"QPushButton:hover {{ color: {hover}; }}"
    )
    return btn


class _Loader(QObject):
    done   = pyqtSignal(dict)
    image  = pyqtSignal(bytes)    # raw ship image bytes
    failed = pyqtSignal(str)

    def __init__(self, killmail_id: int, zkb_hash: str, isk_value: float,
                 ship_type_id: int):
        super().__init__()
        self._kill_id     = killmail_id
        self._zkb_hash    = zkb_hash
        self._isk_value   = isk_value
        self._ship_type_id = ship_type_id

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            from api.killboard import get_kill_summary_data
            data = get_kill_summary_data(self._kill_id, self._zkb_hash, self._isk_value)
            self.done.emit(data)

            # Fetch ship render image separately
            import requests
            r = requests.get(
                f"https://images.evetech.net/types/{self._ship_type_id}/render?size=64",
                timeout=8,
            )
            if r.ok:
                self.image.emit(r.content)
        except Exception as e:
            self.failed.emit(str(e))


class KillSummaryWindow(QWidget):
    def __init__(self, row: dict, parent_pos: QPoint):
        super().__init__()
        self._drag_pos  = QPoint()
        self._kill_id   = row["killmail_id"]
        self._ship_name = row["ship"]
        self._time      = row["time"]
        self._location  = row["location"]

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(340, 150)
        self.resize(420, 300)
        from ui.utils import smart_pos
        self.move(smart_pos(parent_pos, 720, 420, 300, prefer_left=False))

        self._build_ui()

        self._loader = _Loader(
            row["killmail_id"], row["zkb_hash"],
            row["isk_value"],   row["ship_type_id"],
        )
        self._loader.done.connect(self._on_data)
        self._loader.image.connect(self._on_image)
        self._loader.failed.connect(self._on_error)
        self._loader.start()

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget(self)
        root.setObjectName("root")
        root.setStyleSheet(f"""
            #root {{
                background: {DARK_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QPushButton {{
                background: transparent; border: none;
                color: #666; font-size: 12px; padding: 0;
            }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # ── title bar ──
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet(f"background: {HEADER_BG}; border-radius: 8px 8px 0 0;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 6, 0)
        tb.setSpacing(4)

        self._title_lbl = QLabel(f"{self._ship_name}  —  {self._time}")
        self._title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {ACCENT};")
        tb.addWidget(self._title_lbl)
        tb.addStretch()

        web_btn = QPushButton("zK")
        web_btn.setFixedSize(20, 20)
        web_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        web_btn.setToolTip("Open on zKillboard")
        web_btn.setStyleSheet(
            "QPushButton { border: none; color: #446688; font-size: 8px; "
            "font-weight: bold; background: transparent; padding: 0; }"
            "QPushButton:hover { color: #4fc3f7; }"
        )
        web_btn.clicked.connect(
            lambda: webbrowser.open(f"https://zkillboard.com/kill/{self._kill_id}/")
        )
        tb.addWidget(web_btn)

        reset_btn = _icon_btn("↺")
        reset_btn.setToolTip("Reset size")
        reset_btn.clicked.connect(lambda: self.resize(420, 300))
        tb.addWidget(reset_btn)

        close_btn = _icon_btn("✕", hover="#f44336")
        close_btn.clicked.connect(self.close)
        tb.addWidget(close_btn)

        self._layout.addWidget(title_bar)

        # ── loading placeholder ──
        self._loading_lbl = QLabel("  Loading kill details...")
        self._loading_lbl.setStyleSheet(f"color: {DIM}; padding: 12px; font-size: 11px;")
        self._layout.addWidget(self._loading_lbl)

        # ── content area (hidden until loaded) ──
        self._content = QWidget()
        self._content.hide()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(10, 8, 10, 10)
        content_layout.setSpacing(8)

        # ship image + victim info
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        self._ship_img = QLabel()
        self._ship_img.setFixedSize(64, 64)
        self._ship_img.setStyleSheet(
            f"border: 1px solid {BORDER}; border-radius: 4px; background: #0a0a12;"
        )
        self._ship_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_row.addWidget(self._ship_img)

        victim_col = QVBoxLayout()
        victim_col.setSpacing(2)
        self._victim_name  = QLabel()
        self._victim_corp  = QLabel()
        self._victim_ally  = QLabel()
        self._isk_lbl      = QLabel()
        self._location_lbl = QLabel()

        self._victim_name.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._victim_name.setStyleSheet(f"color: {TEXT};")
        self._victim_corp.setStyleSheet("color: #aaaacc; font-size: 11px;")
        self._victim_ally.setStyleSheet("color: #aaaacc; font-size: 11px;")
        self._isk_lbl.setStyleSheet(f"color: {GOLD}; font-size: 11px;")
        self._location_lbl.setStyleSheet("color: #888899; font-size: 10px;")

        for w in (self._victim_name, self._victim_corp, self._victim_ally,
                  self._isk_lbl, self._location_lbl):
            victim_col.addWidget(w)
        victim_col.addStretch()
        info_row.addLayout(victim_col)
        content_layout.addLayout(info_row)

        # divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        content_layout.addWidget(line)

        # final blow
        self._fb_header = QLabel()
        self._fb_header.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: bold;")
        self._fb_detail = QLabel()
        self._fb_detail.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
        self._fb_detail.setWordWrap(True)
        content_layout.addWidget(self._fb_header)
        content_layout.addWidget(self._fb_detail)

        # attackers table
        self._atk_header = QLabel()
        self._atk_header.setStyleSheet("color: #888; font-size: 10px;")
        content_layout.addWidget(self._atk_header)

        self._atk_table = QTableWidget(0, 3)
        self._atk_table.setHorizontalHeaderLabels(["Corp", "Alliance", "Pilots"])
        self._atk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._atk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._atk_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._atk_table.setColumnWidth(2, 50)
        self._atk_table.verticalHeader().setVisible(False)
        self._atk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._atk_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._atk_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._atk_table.setAlternatingRowColors(True)
        self._atk_table.setStyleSheet(f"""
            QTableWidget {{
                background: {ROW_BG}; border: 1px solid {BORDER};
                gridline-color: {BORDER}; color: {TEXT}; font-size: 11px;
            }}
            QHeaderView::section {{
                background: {HEADER_BG}; color: #888; border: none;
                border-bottom: 1px solid {BORDER}; padding: 3px; font-size: 10px;
            }}
            QTableWidget::item {{ padding: 2px 6px; }}
            QTableWidget::item:alternate {{ background: {ROW_ALT}; }}
        """)
        content_layout.addWidget(self._atk_table)

        self._layout.addWidget(self._content)

        # grip
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        self._grip.setStyleSheet("QSizeGrip { background: transparent; }")
        self._grip.raise_()

    # ── data handlers ──────────────────────────────────────────────

    def _on_data(self, data: dict):
        self._loading_lbl.hide()

        v = data["victim"]
        self._victim_name.setText(v["name"])
        self._victim_corp.setText(v["corp"])
        if v["alliance"]:
            self._victim_ally.setText(f"[{v['alliance']}]")
        self._isk_lbl.setText(f"💰 {data['isk_value']}")
        self._location_lbl.setText(self._location)

        fb = data["final_blow"]
        if fb:
            self._fb_header.setText("★  Final blow")
            ally = f" [{fb['alliance']}]" if fb["alliance"] else ""
            self._fb_detail.setText(
                f"{fb['name']}  ·  {fb['corp']}{ally}  ·  {fb['damage']:,} dmg"
            )
        else:
            self._fb_header.setText("Final blow: unknown")

        others = data["other_attackers"]
        total  = data["total_attackers"]
        self._atk_header.setText(
            f"Other attackers  ({total - (1 if fb else 0)} pilots"
            f"{', showing top ' + str(len(others)) if len(others) < total - 1 else ''})"
        )
        self._atk_table.setRowCount(len(others))
        for i, row in enumerate(others):
            corp_item  = QTableWidgetItem(row["corp"])
            ally_item  = QTableWidgetItem(row["alliance"])
            cnt_item   = QTableWidgetItem(str(row["count"]))
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            for item in (corp_item, ally_item, cnt_item):
                item.setTextAlignment(
                    item.textAlignment() or
                    (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                )
            self._atk_table.setItem(i, 0, corp_item)
            self._atk_table.setItem(i, 1, ally_item)
            self._atk_table.setItem(i, 2, cnt_item)

        self._content.show()
        self.adjustSize()

    def _on_image(self, data: bytes):
        pix = QPixmap()
        pix.loadFromData(data)
        self._ship_img.setPixmap(
            pix.scaled(64, 64,
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        )

    def _on_error(self, msg: str):
        self._loading_lbl.setText(f"  Error: {msg[:80]}")

    # ── resize grip ────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - self._grip.width() - 2,
                        self.height() - self._grip.height() - 2)
        self._grip.raise_()

    # ── drag ───────────────────────────────────────────────────────

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
