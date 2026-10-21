import sys, os
os.environ.setdefault('QT_QPA_PLATFORM','wayland')
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QColor, QPalette
app = QApplication(sys.argv)
w = QWidget()
w.setWindowTitle('phase3-fullscreen')
w.setWindowFlags(Qt.WindowType.FramelessWindowHint)
w.setAutoFillBackground(True)
p = w.palette(); p.setColor(QPalette.ColorRole.Window, QColor('#204060')); w.setPalette(p)
for s in QGuiApplication.screens():
    print(s.name(), s.geometry())
scr = next((s for s in QGuiApplication.screens() if s.name() == 'HDMI-A-1'), QGuiApplication.primaryScreen())
w.setScreen(scr)
w.showFullScreen()
w.activateWindow()
w.raise_()
QTimer.singleShot(60000, app.quit)
sys.exit(app.exec())
