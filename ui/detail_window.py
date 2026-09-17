"""
Kill detail popup. Opens beside the overlay when you click a system row.
Loads kill data on a background thread so the UI stays responsive.
"""

import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QSizeGrip
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QMouseEvent

DARK_BG   = "rgba(15, 15, 20, 220)"
HEADER_BG = "#1a1a2e"
ROW_BG    = "#0f0f14"
ROW_ALT   = "#131320"
BORDER    = "#2a2a4a"
TEXT      = "#c8c8d8"
ACCENT    = "#4fc3f7"
DIM       = "#555577"


class _Loader(QObject):
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, system_id: int):
        super().__init__()
        self._system_id = system_id

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            from api.killboard import build_kill_rows
            rows = build_kill_rows(self._system_id)
            self.done.emit(rows)
        except Exception as e:
            self.failed.emit(str(e))


class DetailWindow(QWidget):
    def __init__(self, system_name: str, system_id: int, parent_pos: QPoint):
        super().__init__()
        self._drag_pos = QPoint()
        self._kill_rows: list[dict] = []
        self._summary_window = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(720, 200)

        from ui.utils import smart_pos
        self.move(smart_pos(parent_pos, 340, 720, 200, prefer_left=True))

        self._build_ui(system_name)
        self._load(system_id)

    def _build_ui(self, system_name: str):
        root = QWidget(self)
        root.setObjectName("root")
        root.setStyleSheet(f"""
            #root {{
                background: {DARK_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QLabel {{ color: {TEXT}; }}
            QPushButton {{
                background: transparent; color: {TEXT};
                border: none; font-size: 12px; padding: 0;
            }}
            QPushButton:hover {{ color: #f44336; }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet(f"background: {HEADER_BG}; border-radius: 8px 8px 0 0;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 8, 0)

        lbl = QLabel(f"Kills in {system_name}")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        tb.addWidget(lbl)
        tb.addStretch()

        _s = "QPushButton {{ border: none; color: {}; font-size: 11px; padding: 0; }} QPushButton:hover {{ color: {}; }}"
        reset_btn = QPushButton("↺")
        reset_btn.setFixedSize(18, 18)
        reset_btn.setStyleSheet(_s.format("#666", "#4fc3f7"))
        reset_btn.setToolTip("Reset to default size")
        reset_btn.clicked.connect(lambda: self.resize(720, 200))
        tb.addWidget(reset_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet(_s.format("#666", "#f44336"))
        close_btn.clicked.connect(self.close)
        tb.addWidget(close_btn)

        layout.addWidget(title_bar)

        # status / loading label
        self._status = QLabel("  Loading kill details...")
        self._status.setStyleSheet(f"color: {DIM}; padding: 8px; font-size: 11px;")
        layout.addWidget(self._status)

        # table (hidden until data arrives)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Ship", "Attacker", "When", "Location"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 150)
        self._table.setColumnWidth(1, 210)
        self._table.setColumnWidth(2, 70)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {ROW_BG}; border: none;
                gridline-color: {BORDER}; color: {TEXT}; font-size: 11px;
            }}
            QHeaderView::section {{
                background: {HEADER_BG}; color: #888; border: none;
                border-bottom: 1px solid {BORDER}; padding: 3px; font-size: 10px;
            }}
            QTableWidget::item {{ padding: 3px 6px; }}
            QTableWidget::item:alternate {{ background: {ROW_ALT}; }}
        """)
        self._table.setAlternatingRowColors(True)
        self._table.cellClicked.connect(self._on_kill_clicked)
        self._table.setCursor(Qt.CursorShape.PointingHandCursor)
        self._table.hide()
        layout.addWidget(self._table)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        self._grip.setStyleSheet("QSizeGrip { background: transparent; }")
        self._grip.raise_()

    def _load(self, system_id: int):
        self._loader = _Loader(system_id)
        self._loader.done.connect(self._on_data)
        self._loader.failed.connect(self._on_error)
        self._loader.start()

    def _on_data(self, rows: list):
        self._kill_rows = rows
        self._status.hide()
        if not rows:
            self._status.setText(
                "  zKillboard has no kills on record for this system yet.\n"
                "  ESI kill counts come directly from CCP and update faster.\n"
                "  zKillboard may catch up within a few minutes."
            )
            self._status.show()
            self.resize(720, 80)
            return

        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            ship_item     = QTableWidgetItem(row["ship"])
            attacker_item = QTableWidgetItem(row.get("attacker", "Unknown"))
            time_item     = QTableWidgetItem(row["time"])
            loc_item      = QTableWidgetItem(row["location"])

            f = ship_item.font()
            f.setUnderline(True)
            ship_item.setFont(f)
            ship_item.setToolTip("Click to open on zKillboard")
            ship_item.setForeground(QColor(ACCENT))

            attacker_item.setForeground(QColor("#aaaacc"))
            time_item.setForeground(QColor("#888899"))
            if "gate" in row["location"].lower():
                loc_item.setForeground(QColor("#ffc107"))

            for item in (ship_item, attacker_item, time_item, loc_item):
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            self._table.setItem(i, 0, ship_item)
            self._table.setItem(i, 1, attacker_item)
            self._table.setItem(i, 2, time_item)
            self._table.setItem(i, 3, loc_item)

        self._table.show()
        row_h = self._table.rowHeight(0) if rows else 24
        self.resize(720, min(480, 60 + len(rows) * row_h))

    def _on_kill_clicked(self, row: int, _col: int):
        if row >= len(self._kill_rows):
            return
        from ui.kill_summary_window import KillSummaryWindow
        if self._summary_window:
            self._summary_window.close()
        self._summary_window = KillSummaryWindow(self._kill_rows[row], self.pos())
        self._summary_window.show()

    def _on_error(self, msg: str):
        self._status.setText(f"  Error loading kills: {msg[:60]}")

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
