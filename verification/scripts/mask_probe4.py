import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QRegion

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
w.resize(300, 300)
w.show()
print("shown transparent", flush=True)
QTimer.singleShot(500, lambda: (w.windowHandle().setMask(QRegion(50,50,100,100)), print("partial", flush=True)))
QTimer.singleShot(1000, lambda: (w.windowHandle().setMask(QRegion()), print("empty", flush=True)))
QTimer.singleShot(1500, app.quit)
sys.exit(app.exec())
