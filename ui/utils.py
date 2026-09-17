from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication


def smart_pos(anchor_pos: QPoint, anchor_w: int,
              win_w: int, win_h: int,
              prefer_left: bool = True) -> QPoint:
    """
    Place a window beside an anchor rectangle, choosing the side that has room.
    Falls back to clamping within screen bounds if neither side fits cleanly.
    """
    screen = QApplication.primaryScreen().availableGeometry()
    gap = 8

    left_x  = anchor_pos.x() - win_w - gap
    right_x = anchor_pos.x() + anchor_w + gap

    fits_left  = left_x >= screen.left()
    fits_right = right_x + win_w <= screen.right()

    if prefer_left:
        x = left_x if fits_left else (right_x if fits_right else left_x)
    else:
        x = right_x if fits_right else (left_x if fits_left else right_x)

    x = max(screen.left(), min(x, screen.right() - win_w))
    y = max(screen.top(), min(anchor_pos.y(), screen.bottom() - win_h))

    return QPoint(x, y)
