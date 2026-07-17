#!/usr/bin/env python3
"""Loading screen shown during first-run setup. Uses system PyQt5."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "linuxfb:fb=/dev/fb0:tty=/dev/tty1")
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

class LoadingScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:#0b1220;")
        self.dots = 0
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignCenter)
        title = QLabel("Setting up the app")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#f9fafb; font-size:24px; font-weight:bold;")
        sub = QLabel("First-run install in progress.\nThis may take a few minutes.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#9ca3af; font-size:14px; padding-top:12px;")
        self.dot_lbl = QLabel("Loading")
        self.dot_lbl.setAlignment(Qt.AlignCenter)
        self.dot_lbl.setStyleSheet("color:#60a5fa; font-size:20px; padding-top:30px;")
        v.addWidget(title); v.addWidget(sub); v.addWidget(self.dot_lbl)
        self.showFullScreen()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
    def tick(self):
        self.dots = (self.dots + 1) % 4
        self.dot_lbl.setText("Loading" + "." * self.dots)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = LoadingScreen()
    sys.exit(app.exec_())
