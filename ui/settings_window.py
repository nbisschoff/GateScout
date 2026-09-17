"""
Settings window — transparency slider, volume slider, and alert sound picker.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QButtonGroup, QRadioButton, QFrame, QSizeGrip,
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent

DARK_BG   = "rgba(15, 15, 20, 225)"
HEADER_BG = "#1a1a2e"
BORDER    = "#2a2a4a"
TEXT      = "#c8c8d8"
ACCENT    = "#4fc3f7"
DIM       = "#555577"

_SLIDER_STYLE = f"""
    QSlider::groove:horizontal {{
        height: 4px; background: {BORDER}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT}; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px; margin: -5px 0;
        background: {ACCENT}; border-radius: 7px;
    }}
"""


class SettingsWindow(QWidget):
    opacity_changed = pyqtSignal(float)
    sound_changed   = pyqtSignal(str)
    volume_changed  = pyqtSignal(float)
    save_requested  = pyqtSignal(float, str, float)  # opacity, sound, volume

    def __init__(self, parent_pos: QPoint, current_opacity: float,
                 current_sound: str, current_volume: float):
        super().__init__()
        self._drag_pos       = QPoint()
        self._current_opacity = current_opacity
        self._current_sound   = current_sound
        self._current_volume  = current_volume

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
        from settings_manager import SOUNDS

        root = QWidget(self)
        root.setObjectName("root")
        root.setStyleSheet(f"""
            #root {{
                background: {DARK_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QPushButton {{ background: transparent; color: #666; border: none; font-size: 12px; padding: 0; }}
            QPushButton:hover {{ color: #f44336; }}
            QRadioButton {{ color: {TEXT}; font-size: 12px; spacing: 8px; }}
            QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 7px; border: 1px solid #444466; }}
            QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── title bar ──
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet(f"background: {HEADER_BG}; border-radius: 8px 8px 0 0;")
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 8, 0)
        lbl = QLabel("⚙  Settings")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {ACCENT};")
        tb.addWidget(lbl)
        tb.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.clicked.connect(self.close)
        tb.addWidget(close_btn)
        layout.addWidget(title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 16)
        body_layout.setSpacing(14)

        # ── overlay transparency ──
        body_layout.addWidget(self._section_label("OVERLAY TRANSPARENCY"))
        self._opacity_slider, op_row = self._slider_row(
            minimum=30, maximum=100,
            value=int(self._current_opacity * 100),
            fmt=lambda v: f"{v}%",
            on_change=self._on_opacity_changed,
            attr="_opacity_lbl",
        )
        body_layout.addLayout(op_row)

        body_layout.addWidget(self._divider())

        # ── alert volume ──
        body_layout.addWidget(self._section_label("ALERT VOLUME"))
        self._volume_slider, vol_row = self._slider_row(
            minimum=0, maximum=100,
            value=int(self._current_volume * 100),
            fmt=lambda v: f"{v}%",
            on_change=self._on_volume_changed,
            attr="_volume_lbl",
        )
        body_layout.addLayout(vol_row)

        body_layout.addWidget(self._divider())

        # ── alert sound ──
        body_layout.addWidget(self._section_label("ALERT SOUND"))

        self._sound_group = QButtonGroup(self)
        for name in SOUNDS:
            row = QHBoxLayout()
            row.setSpacing(8)
            rb = QRadioButton(name)
            if name == self._current_sound:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, n=name: self._on_sound_changed(n) if checked else None)
            self._sound_group.addButton(rb)

            preview_btn = QPushButton("▶")
            preview_btn.setFixedSize(22, 22)
            preview_btn.setStyleSheet(
                f"QPushButton {{ border: 1px solid {BORDER}; border-radius: 4px; "
                f"color: {ACCENT}; font-size: 10px; padding: 0; }}"
                f"QPushButton:hover {{ background: {BORDER}; }}"
            )
            preview_btn.setToolTip(f"Preview: {name}")
            preview_btn.clicked.connect(lambda _, n=name: self._preview(n))

            row.addWidget(rb)
            row.addStretch()
            row.addWidget(preview_btn)
            body_layout.addLayout(row)

        layout.addWidget(body)

        # ── save button ──
        footer = QWidget()
        footer.setStyleSheet(f"background: {HEADER_BG}; border-radius: 0 0 8px 8px;")
        ft = QHBoxLayout(footer)
        ft.setContentsMargins(16, 8, 16, 10)
        ft.addStretch()
        save_btn = QPushButton("Save settings")
        save_btn.setFixedWidth(160)
        save_btn.setFixedHeight(28)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: #07070f;
                border: none; border-radius: 5px;
                font-size: 12px; font-weight: 600; padding: 0 18px;
            }}
            QPushButton:hover {{ background: #81d4fa; }}
        """)
        save_btn.clicked.connect(self._on_save)
        ft.addWidget(save_btn)
        ft.addStretch()
        layout.addWidget(footer)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        self._grip.setStyleSheet("QSizeGrip { background: transparent; }")
        self._grip.raise_()
        self.adjustSize()

    # ── helpers ────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {DIM}; font-size: 10px; letter-spacing: 1px;")
        return lbl

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        return line

    def _slider_row(self, minimum, maximum, value, fmt, on_change, attr):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setValue(value)
        slider.setStyleSheet(_SLIDER_STYLE)

        val_lbl = QLabel(fmt(value))
        val_lbl.setFixedWidth(36)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        setattr(self, attr, val_lbl)

        slider.valueChanged.connect(lambda v: (val_lbl.setText(fmt(v)), on_change(v)))

        row = QHBoxLayout()
        row.addWidget(slider)
        row.addWidget(val_lbl)
        return slider, row

    # ── signal handlers ─────────────────────────────────────────────

    def _on_opacity_changed(self, value: int):
        self.opacity_changed.emit(value / 100)

    def _on_volume_changed(self, value: int):
        self._current_volume = value / 100
        self.volume_changed.emit(self._current_volume)

    def _on_sound_changed(self, name: str):
        self._current_sound = name
        self.sound_changed.emit(name)

    def _on_save(self):
        checked = self._sound_group.checkedButton()
        sound = checked.text() if checked else self._current_sound
        self.save_requested.emit(
            self._opacity_slider.value() / 100,
            sound,
            self._volume_slider.value() / 100,
        )
        self.close()

    def _preview(self, name: str):
        from settings_manager import play_sound
        play_sound(name, self._current_volume)

    # ── window boilerplate ──────────────────────────────────────────

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
