from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QPaintEvent, QPainter, QPen, QPixmap, QShowEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StartupSplash(QWidget):
    CANVAS_SIZE = 440
    BASE_PINK = QColor("#f79dc9")
    HOT_PINK = QColor("#fb74b8")
    DEEP_PURPLE = QColor("#9349a2")

    def __init__(self, asset_root: Path):
        super().__init__()
        self._progress = 3
        self._ring_rotation = 0.0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(33)
        self._animation_timer.timeout.connect(self._advance_ring_animation)
        self.setObjectName("StartupSplash")
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.CANVAS_SIZE, self.CANVAS_SIZE)

        self.setStyleSheet(
            """
            QLabel {
                background: transparent;
                border: none;
                color: #493342;
                font-family: "Segoe UI";
            }
            QLabel#Brand {
                color: #9349a2;
                font-size: 10px;
                font-weight: 800;
            }
            QLabel#Title {
                color: #5a315e;
                font-size: 18px;
                font-weight: 900;
            }
            QLabel#Detail {
                color: #493342;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#Aside {
                color: #9a627f;
                font-size: 9px;
            }
            QLabel#Progress {
                color: #e74f9e;
                font-size: 12px;
                font-weight: 800;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(54, 30, 54, 34)
        layout.setSpacing(2)

        self.brand = QLabel("MINI KLOUDY")
        self.brand.setObjectName("Brand")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.art = QLabel()
        self.art.setObjectName("MiniKloudyArt")
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setFixedHeight(220)
        artwork = QPixmap(str(Path(asset_root) / "mini-kloudy.png"))
        if artwork.isNull():
            self.art.setText("K")
            self.art.setStyleSheet("color: #f79dc9; font-size: 112px; font-weight: 900;")
        else:
            self.art.setPixmap(
                artwork.scaled(
                    245,
                    245,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self.title = QLabel("Kloudy's Forza Painter Suite")
        self.title.setObjectName("Title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.detail = QLabel("Getting your paint shelf ready...")
        self.detail.setObjectName("Detail")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)

        self.aside = QLabel("Counting rectangles with the clipboard upside down.")
        self.aside.setObjectName("Aside")
        self.aside.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.aside.setWordWrap(True)

        self.progress_label = QLabel("3%")
        self.progress_label.setObjectName("Progress")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.brand)
        layout.addWidget(self.art)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addWidget(self.aside)
        layout.addWidget(self.progress_label)

    @property
    def progress_value(self) -> int:
        return self._progress

    def set_progress(self, done: int, total: int) -> None:
        self._progress = int(max(0, min(100, (float(done) / max(1.0, float(total))) * 100.0)))
        self.progress_label.setText(f"{max(3, self._progress)}%")
        self.update()

    def set_status(self, message: str, aside: str) -> None:
        self.detail.setText(message)
        self.aside.setText(aside)

    def _advance_ring_animation(self) -> None:
        self._ring_rotation = (self._ring_rotation + 1.8) % 360.0
        self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._animation_timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        shadow = QRectF(11, 16, self.width() - 22, self.height() - 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(147, 73, 162, 42))
        painter.drawEllipse(shadow)

        disc = QRectF(10, 8, self.width() - 20, self.height() - 20)
        painter.setBrush(QColor("#fffafd"))
        painter.setPen(QPen(self.BASE_PINK, 8))
        painter.drawEllipse(disc)

        inner = disc.adjusted(13, 13, -13, -13)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#f8d7e8"), 8))
        painter.drawEllipse(inner)

        progress_pen = QPen(self.HOT_PINK, 8)
        progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(progress_pen)
        progress_start = int((90.0 - self._ring_rotation) * 16)
        painter.drawArc(inner, progress_start, -int(360 * max(3, self._progress) * 16 / 100))

        accent = disc.adjusted(24, 24, -24, -24)
        accent_pen = QPen(self.DEEP_PURPLE, 3)
        accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(accent_pen)
        accent_rotation = self._ring_rotation * 0.72
        painter.drawArc(accent, int((205.0 + accent_rotation) * 16), 34 * 16)
        painter.drawArc(accent, int((25.0 + accent_rotation) * 16), 34 * 16)
