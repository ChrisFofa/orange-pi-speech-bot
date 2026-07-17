#!/usr/bin/env python3
from __future__ import annotations

import math
import os
import random
import sys

if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "linuxfb"

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


# ============================================================
# Orange Pi 3.5-inch Face Widget
# ============================================================
#
# Internal logical screen:
#   480 x 320
#
# States:
#   idle
#   listening
#   thinking
#   talking
#   sleeping
#   error -> visually uses sleeping face
#
# ============================================================


LOGICAL_W = 480
LOGICAL_H = 320


# ============================================================
# Color Palette
# ============================================================

SKIN = QColor(240, 201, 160)
MARK_DARK = QColor(92, 64, 51)
NOSE_COLOR = QColor(74, 51, 40)

EYE_OUTLINE = QColor(232, 221, 208)

PUPIL_DARK = QColor(42, 26, 14)
PUPIL_MID = QColor(61, 40, 22)

LISTENING_PUPIL = QColor(42, 58, 32)
THINKING_PUPIL = QColor(58, 45, 86)

RING_GREEN = QColor(100, 220, 160)
THINKING_BLUE = QColor(100, 130, 255)


# ============================================================
# Face Layout Settings
# ============================================================

CFG = {
    "faceScale": 1.08,
    "faceY": -45,

    "eyeSpacing": 0.62,
    "eyeY": 0.54,
    "eyeW": 0.200,
    "eyeH": 0.205,
    "pupil": 0.65,

    "triW": 0.45,
    "triDepth": 0.66,

    "nose": 0.050,

    "mouthY": 0.86,
    "mouthW": 0.22,
    "mouthH": 0.13,
    "mouthMin": 0.06,
    "mouthAnim": 1.05,
}


# ============================================================
# Face Widget
# ============================================================

class FaceWidget(QWidget):
    """
    Animated face widget for the kiosk.

    Public method:
      set_state(state: str)

    Valid states:
      idle, listening, thinking, talking, sleeping, error

    Note:
      error intentionally draws like sleeping, so the kiosk does not show
      an angry/worried face during setup or network issues.
    """

    STATES = [
        "idle",
        "listening",
        "thinking",
        "talking",
        "sleeping",
        "error",
    ]

    def __init__(
        self,
        parent=None,
        debug_cycle_on_tap: bool = False,
    ):
        super().__init__(parent)

        self.debug_cycle_on_tap = debug_cycle_on_tap

        self.state = "idle"
        self.frame = 0

        self.blink_timer = 0
        self.is_blinking = False
        self.blink_frame = 0

        self.pupil_offset_x = 0.0
        self.pupil_offset_y = 0.0
        self.pupil_target_x = 0.0
        self.pupil_target_y = 0.0
        self.next_look_timer = 0

        self.zzz_particles: list[dict[str, float]] = []
        self.thought_particles: list[dict[str, float]] = []

        self.setMinimumSize(160, 107)
        self.setAutoFillBackground(False)

        # About 20 FPS.
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(50)

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def set_state(self, state: str) -> None:
        """
        Set animation state.

        Unknown state falls back to idle.
        """

        state = (state or "idle").strip().lower()

        if state not in self.STATES:
            state = "idle"

        if self.state == state:
            return

        self.state = state
        self.frame = 0

        self.blink_timer = 0
        self.is_blinking = False
        self.blink_frame = 0

        self.pupil_offset_x = 0.0
        self.pupil_offset_y = 0.0
        self.pupil_target_x = 0.0
        self.pupil_target_y = 0.0

        self.zzz_particles = []
        self.thought_particles = []

        self.update()

    def get_state(self) -> str:
        return self.state

    # --------------------------------------------------------
    # Coordinate Helpers
    # --------------------------------------------------------

    @staticmethod
    def _x(x: float, w: float, value: float) -> float:
        return x + w * value

    @staticmethod
    def _y(y: float, h: float, value: float) -> float:
        return y + h * value

    @staticmethod
    def _s(w: float, h: float, value: float) -> float:
        return min(w, h) * value

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    # --------------------------------------------------------
    # Animation Tick
    # --------------------------------------------------------

    def _tick(self) -> None:
        self.frame += 1

        if self.state == "idle":
            self._tick_idle()

        elif self.state == "listening":
            self._tick_listening()

        elif self.state == "thinking":
            self._tick_thinking()

        elif self.state == "talking":
            self._tick_talking()

        elif self.state == "sleeping":
            self._tick_sleeping()

        elif self.state == "error":
            # Error intentionally uses sleeping behavior.
            self._tick_sleeping()

        self._smooth_pupils()
        self.update()

    def _tick_idle(self) -> None:
        if not self.is_blinking:
            self.blink_timer += 1

            if self.blink_timer > random.randint(40, 100):
                self.is_blinking = True
                self.blink_frame = 0
                self.blink_timer = 0

        else:
            self.blink_frame += 1

            if self.blink_frame > 6:
                self.is_blinking = False

        self.next_look_timer += 1

        if self.next_look_timer > random.randint(30, 80):
            self.pupil_target_x = random.uniform(-0.30, 0.30)
            self.pupil_target_y = random.uniform(-0.20, 0.20)
            self.next_look_timer = 0

    def _tick_listening(self) -> None:
        self.pupil_target_x = 0.0
        self.pupil_target_y = 0.0

    def _tick_talking(self) -> None:
        self.pupil_target_x = 0.0
        self.pupil_target_y = 0.10

    def _tick_thinking(self) -> None:
        self.pupil_target_x = math.sin(self.frame * 0.08) * 0.30
        self.pupil_target_y = -0.15

        if self.frame % 16 == 0:
            self.thought_particles.append(
                {
                    "x": random.uniform(0.38, 0.62),
                    "y": random.uniform(0.14, 0.22),
                    "age": 0.0,
                    "size": random.uniform(5.0, 9.0),
                }
            )

        for p in self.thought_particles:
            p["age"] += 1.0
            p["y"] -= 0.004
            p["size"] += 0.08

        self.thought_particles = [
            p for p in self.thought_particles
            if p["age"] < 35
        ]

    def _tick_sleeping(self) -> None:
        self.pupil_target_x = 0.0
        self.pupil_target_y = 0.0

        if self.frame % 24 == 0:
            self.zzz_particles.append(
                {
                    "x": 0.72,
                    "y": 0.32,
                    "age": 0.0,
                    "size": 10.0,
                }
            )

        for p in self.zzz_particles:
            p["age"] += 1.0
            p["x"] += 0.004
            p["y"] -= 0.006
            p["size"] += 0.16

        self.zzz_particles = [
            p for p in self.zzz_particles
            if p["age"] < 40
        ]

    def _smooth_pupils(self) -> None:
        self.pupil_offset_x += (
            self.pupil_target_x - self.pupil_offset_x
        ) * 0.15

        self.pupil_offset_y += (
            self.pupil_target_y - self.pupil_offset_y
        ) * 0.15

    # --------------------------------------------------------
    # Paint
    # --------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        widget_w = max(1, self.width())
        widget_h = max(1, self.height())

        painter.fillRect(0, 0, widget_w, widget_h, SKIN)

        # Keep the simulation at a 480x320 logical aspect ratio.
        scale = min(widget_w / LOGICAL_W, widget_h / LOGICAL_H)

        draw_w = LOGICAL_W * scale
        draw_h = LOGICAL_H * scale

        off_x = (widget_w - draw_w) / 2
        off_y = (widget_h - draw_h) / 2

        painter.save()
        painter.translate(off_x, off_y)
        painter.scale(scale, scale)
        painter.setClipRect(QRectF(0, 0, LOGICAL_W, LOGICAL_H))

        self._draw_screen(painter)

        painter.restore()
        painter.end()

    def _draw_screen(self, painter: QPainter) -> None:
        painter.fillRect(0, 0, LOGICAL_W, LOGICAL_H, SKIN)

        face_h = LOGICAL_H * CFG["faceScale"]
        face_w = LOGICAL_W * 0.98

        x = (LOGICAL_W - face_w) / 2
        y = (LOGICAL_H - face_h) / 2 + CFG["faceY"]

        draw_state = "sleeping" if self.state == "error" else self.state

        breath = (
            math.sin(self.frame * 0.05) * 2.0
            if draw_state == "sleeping"
            else 0.0
        )

        self._draw_face_base(painter, x, y, face_w, face_h, breath)

        if draw_state == "idle":
            self._draw_idle(painter, x, y, face_w, face_h)

        elif draw_state == "listening":
            self._draw_listening(painter, x, y, face_w, face_h)

        elif draw_state == "thinking":
            self._draw_thinking(painter, x, y, face_w, face_h)

        elif draw_state == "talking":
            self._draw_talking(painter, x, y, face_w, face_h)

        elif draw_state == "sleeping":
            self._draw_sleeping(painter, x, y, face_w, face_h, breath)

    # --------------------------------------------------------
    # Face Base
    # --------------------------------------------------------

    def _draw_face_base(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        breath: float = 0.0,
    ) -> None:
        tri_top = self._y(y, h, -0.08) + breath * 0.3
        tri_bottom = self._y(y, h, CFG["triDepth"]) + breath * 0.5

        tri_w = self._s(w, h, CFG["triW"])
        cx = self._x(x, w, 0.50)

        painter.setBrush(QBrush(MARK_DARK))
        painter.setPen(Qt.NoPen)

        path = QPainterPath()
        path.moveTo(cx - tri_w, tri_top)
        path.lineTo(cx + tri_w, tri_top)
        path.quadTo(
            cx + tri_w * 0.15,
            tri_bottom * 0.70,
            cx,
            tri_bottom,
        )
        path.quadTo(
            cx - tri_w * 0.15,
            tri_bottom * 0.70,
            cx - tri_w,
            tri_top,
        )
        path.closeSubpath()

        painter.drawPath(path)

        self._draw_nose(painter, x, y, w, h, tri_bottom)

    def _draw_nose(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        tri_bottom: float,
    ) -> None:
        nx = self._x(x, w, 0.50)
        ny = tri_bottom + self._s(w, h, 0.02)

        nw = self._s(w, h, CFG["nose"])
        nh = self._s(w, h, CFG["nose"])

        painter.setBrush(QBrush(NOSE_COLOR))
        painter.setPen(Qt.NoPen)

        path = QPainterPath()
        path.moveTo(nx - nw, ny - nh * 0.30)
        path.quadTo(nx - nw * 0.30, ny - nh, nx, ny - nh * 0.60)
        path.quadTo(nx + nw * 0.30, ny - nh, nx + nw, ny - nh * 0.30)
        path.quadTo(nx + nw * 0.50, ny + nh * 0.50, nx, ny + nh * 0.30)
        path.quadTo(nx - nw * 0.50, ny + nh * 0.50, nx - nw, ny - nh * 0.30)
        path.closeSubpath()

        painter.drawPath(path)

    # --------------------------------------------------------
    # Eye Helpers
    # --------------------------------------------------------

    def _eye_centers(self) -> tuple[float, float, float]:
        left = 0.50 - CFG["eyeSpacing"] / 2
        right = 0.50 + CFG["eyeSpacing"] / 2
        ey = CFG["eyeY"]

        return left, right, ey

    def _draw_eye(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        cx_value: float,
        cy_value: float,
        openness: float,
        dx: float,
        dy: float,
        scale: float = 1.0,
        iris_color: QColor | None = None,
        height_scale: float = 1.0,
    ) -> None:
        cx = self._x(x, w, cx_value)
        cy = self._y(y, h, cy_value)

        rx = self._s(w, h, CFG["eyeW"]) * scale
        ry = self._s(w, h, CFG["eyeH"]) * scale * height_scale

        openness = self._clamp(openness, 0.0, 1.0)

        if openness <= 0.05:
            painter.setPen(
                QPen(
                    MARK_DARK,
                    max(2, int(rx * 0.045)),
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.setBrush(Qt.NoBrush)

            path = QPainterPath()
            path.moveTo(cx - rx * 0.85, cy)
            path.quadTo(cx, cy + ry * 0.15, cx + rx * 0.85, cy)

            painter.drawPath(path)
            return

        actual_ry = max(1.0, ry * openness)

        eye_grad = QRadialGradient(
            cx - rx * 0.10,
            cy - actual_ry * 0.15,
            max(rx, actual_ry),
        )

        eye_grad.setColorAt(0.00, QColor(255, 255, 255))
        eye_grad.setColorAt(0.90, QColor(250, 248, 244))
        eye_grad.setColorAt(1.00, EYE_OUTLINE)

        painter.setBrush(QBrush(eye_grad))
        painter.setPen(
            QPen(
                QColor(180, 160, 140, 75),
                max(1, int(rx * 0.012)),
            )
        )

        painter.drawEllipse(
            QRectF(
                cx - rx,
                cy - actual_ry,
                rx * 2,
                actual_ry * 2,
            )
        )

        iris_r = max(1.0, min(rx, actual_ry) * CFG["pupil"])
        max_shift = rx * 0.18

        ix = cx + dx * max_shift
        iy = cy + dy * max_shift * 0.80

        col = iris_color if iris_color is not None else PUPIL_MID

        iris_grad = QRadialGradient(ix, iy, iris_r)
        iris_grad.setColorAt(
            0.00,
            QColor(col.red(), col.green(), col.blue(), 255),
        )
        iris_grad.setColorAt(
            0.60,
            QColor(col.red(), col.green(), col.blue(), 245),
        )
        iris_grad.setColorAt(
            1.00,
            QColor(60, 40, 20, 92),
        )

        painter.setBrush(QBrush(iris_grad))
        painter.setPen(Qt.NoPen)

        painter.drawEllipse(
            QRectF(
                ix - iris_r,
                iy - iris_r,
                iris_r * 2,
                iris_r * 2,
            )
        )

        pupil_r = iris_r * 0.60

        painter.setBrush(QBrush(PUPIL_DARK))
        painter.drawEllipse(
            QRectF(
                ix - pupil_r,
                iy - pupil_r,
                pupil_r * 2,
                pupil_r * 2,
            )
        )

        highlight_r = iris_r * 0.30

        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(
            QRectF(
                ix - iris_r * 0.28 - highlight_r,
                iy - iris_r * 0.30 - highlight_r * 0.85,
                highlight_r * 2,
                highlight_r * 1.7,
            )
        )

        small_r = highlight_r * 0.35

        painter.setBrush(QBrush(QColor(255, 255, 255, 105)))
        painter.drawEllipse(
            QRectF(
                ix + iris_r * 0.25 - small_r,
                iy + iris_r * 0.20 - small_r,
                small_r * 2,
                small_r * 2,
            )
        )

    def _draw_both_eyes(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        openness: float,
        dx: float,
        dy: float,
        scale: float = 1.0,
        iris_color: QColor | None = None,
        height_scale: float = 1.0,
        breath: float = 0.0,
    ) -> None:
        left, right, ey = self._eye_centers()

        y2 = y + breath

        self._draw_eye(
            painter,
            x,
            y2,
            w,
            h,
            left,
            ey,
            openness,
            dx,
            dy,
            scale,
            iris_color,
            height_scale,
        )

        self._draw_eye(
            painter,
            x,
            y2,
            w,
            h,
            right,
            ey,
            openness,
            dx,
            dy,
            scale,
            iris_color,
            height_scale,
        )

    # --------------------------------------------------------
    # Mouth Helpers
    # --------------------------------------------------------

    def _draw_mouth_smile(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        y_value: float | None = None,
        width_value: float | None = None,
        curve_value: float = 0.04,
    ) -> None:
        if y_value is None:
            y_value = CFG["mouthY"]

        if width_value is None:
            width_value = CFG["mouthW"]

        cx = self._x(x, w, 0.50)
        cy = self._y(y, h, y_value)

        mw = self._s(w, h, width_value)
        mc = self._s(w, h, curve_value)

        painter.setPen(
            QPen(
                MARK_DARK,
                max(2, int(mw * 0.04)),
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.setBrush(Qt.NoBrush)

        path = QPainterPath()
        path.moveTo(cx - mw / 2, cy)
        path.quadTo(cx, cy + mc, cx + mw / 2, cy)

        painter.drawPath(path)

    def _draw_mouth_flat(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        width: float,
        alpha: int = 150,
    ) -> None:
        color = QColor(
            MARK_DARK.red(),
            MARK_DARK.green(),
            MARK_DARK.blue(),
            alpha,
        )

        painter.setPen(
            QPen(
                color,
                max(2, int(width * 0.04)),
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )

        painter.drawLine(
            int(cx - width / 2),
            int(cy),
            int(cx + width / 2),
            int(cy),
        )

    def _draw_mouth_ellipse(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        mw: float,
        mh: float,
    ) -> None:
        mouth_grad = QRadialGradient(cx, cy, max(mw, mh) / 2)
        mouth_grad.setColorAt(0.00, QColor(74, 32, 24))
        mouth_grad.setColorAt(1.00, QColor(42, 16, 10))

        painter.setBrush(QBrush(mouth_grad))
        painter.setPen(QPen(MARK_DARK, max(1, int(mw * 0.06))))

        painter.drawEllipse(
            QRectF(
                cx - mw / 2,
                cy - mh / 2,
                mw,
                mh,
            )
        )

    def _draw_open_mouth(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        amount: float,
    ) -> None:
        amount = self._clamp(amount, 0.0, 1.0)

        cx = self._x(x, w, 0.50)
        cy = self._y(y, h, CFG["mouthY"])

        animated_amount = self._clamp(
            CFG["mouthMin"] + amount * CFG["mouthAnim"],
            0.0,
            1.0,
        )

        mw = self._s(w, h, CFG["mouthW"]) * animated_amount
        mh = self._s(w, h, CFG["mouthH"]) * animated_amount

        self._draw_mouth_ellipse(painter, cx, cy, mw, mh)

    # --------------------------------------------------------
    # State Drawing
    # --------------------------------------------------------

    def _draw_idle(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        openness = 1.0

        if self.is_blinking:
            t = self.blink_frame / 6.0
            openness = max(0.0, 1.0 - math.sin(t * math.pi) * 1.20)

        self._draw_both_eyes(
            painter,
            x,
            y,
            w,
            h,
            openness,
            self.pupil_offset_x,
            self.pupil_offset_y,
        )

        self._draw_mouth_smile(painter, x, y, w, h)

    def _draw_listening(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        pulse = 1.0 + math.sin(self.frame * 0.10) * 0.04

        self._draw_both_eyes(
            painter,
            x,
            y,
            w,
            h,
            1.0,
            self.pupil_offset_x,
            self.pupil_offset_y,
            scale=1.06 * pulse,
            iris_color=LISTENING_PUPIL,
        )

        size = self._s(
            w,
            h,
            0.025 + math.sin(self.frame * 0.15) * 0.008,
        )

        cx = self._x(x, w, 0.50)
        cy = self._y(y, h, CFG["mouthY"])

        self._draw_mouth_ellipse(
            painter,
            cx,
            cy,
            size * 2,
            size * 2,
        )

        ring_alpha = int(25 + math.sin(self.frame * 0.12) * 10)
        ring_r = self._s(
            w,
            h,
            0.45 + math.sin(self.frame * 0.08) * 0.025,
        )

        painter.setPen(
            QPen(
                QColor(
                    RING_GREEN.red(),
                    RING_GREEN.green(),
                    RING_GREEN.blue(),
                    ring_alpha,
                ),
                max(1, int(self._s(w, h, 0.004))),
                Qt.DashLine,
            )
        )
        painter.setBrush(Qt.NoBrush)

        painter.drawEllipse(
            QRectF(
                self._x(x, w, 0.50) - ring_r,
                self._y(y, h, 0.50) - ring_r * 0.78,
                ring_r * 2,
                ring_r * 1.56,
            )
        )

    def _draw_thinking(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        dx = math.sin(self.frame * 0.18) * 0.30

        self._draw_both_eyes(
            painter,
            x,
            y,
            w,
            h,
            1.0,
            dx,
            -0.15,
            iris_color=THINKING_PUPIL,
        )

        self._draw_mouth_smile(
            painter,
            x,
            y,
            w,
            h,
            CFG["mouthY"],
            CFG["mouthW"] * 0.80,
            0.025,
        )

        for p in self.thought_particles:
            alpha = max(0, 166 - int(p["age"] * 5))
            size = max(3, int(p["size"]))

            painter.setBrush(
                QBrush(
                    QColor(
                        THINKING_BLUE.red(),
                        THINKING_BLUE.green(),
                        THINKING_BLUE.blue(),
                        alpha,
                    )
                )
            )
            painter.setPen(Qt.NoPen)

            painter.drawEllipse(
                QRectF(
                    self._x(x, w, p["x"]) - size / 2,
                    self._y(y, h, p["y"]) - size / 2,
                    size,
                    size,
                )
            )

    def _draw_talking(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        self._draw_both_eyes(
            painter,
            x,
            y,
            w,
            h,
            1.0,
            self.pupil_offset_x,
            self.pupil_offset_y,
        )

        amount = (
            math.sin(self.frame * 0.30) * 0.50
            + math.sin(self.frame * 0.47) * 0.30
            + math.sin(self.frame * 0.71) * 0.20
        )

        amount = (amount + 1.0) / 2.0

        self._draw_open_mouth(painter, x, y, w, h, amount)

    def _draw_sleeping(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        breath: float,
    ) -> None:
        self._draw_both_eyes(
            painter,
            x,
            y,
            w,
            h,
            0.0,
            0.0,
            0.0,
            breath=breath,
        )

        mouth_x = self._x(x, w, 0.50)
        mouth_y = self._y(y, h, CFG["mouthY"]) + breath
        mouth_w = self._s(w, h, 0.08)

        self._draw_mouth_flat(
            painter,
            mouth_x,
            mouth_y,
            mouth_w,
            alpha=150,
        )

        for p in self.zzz_particles:
            alpha = max(0, 200 - int(p["age"] * 5))

            painter.setPen(QColor(100, 120, 255, alpha))
            painter.setFont(
                QFont(
                    "Sans",
                    max(8, int(p["size"])),
                    QFont.Bold,
                )
            )

            painter.drawText(
                int(self._x(x, w, p["x"])),
                int(self._y(y, h, p["y"])),
                "z",
            )

    # --------------------------------------------------------
    # Optional Debug Tap
    # --------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if not self.debug_cycle_on_tap:
            return

        try:
            idx = self.STATES.index(self.state)
        except ValueError:
            idx = 0

        next_state = self.STATES[(idx + 1) % len(self.STATES)]
        self.set_state(next_state)


# ============================================================
# Standalone Test
# ============================================================

def main() -> None:
    """
    Test with:

      FULLSCREEN=0 python3 face_widget.py

    Tap/click the face to cycle states.
    """

    app = QApplication(sys.argv)

    face = FaceWidget(debug_cycle_on_tap=True)
    face.setWindowTitle("Orange Pi 3.5 Face Test")

    fullscreen = os.getenv("FULLSCREEN", "1").strip() != "0"

    if fullscreen:
        face.showFullScreen()
    else:
        face.resize(LOGICAL_W, LOGICAL_H)
        face.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()