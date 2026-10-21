import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer

LOG = open("verification/logs/live/tray_probe.log", "w", buffering=1)
app = QApplication(sys.argv)
tray = QSystemTrayIcon(QIcon.fromTheme("applications-system"))
tray.setToolTip("slugcatpet phase0 tray")
menu = QMenu()
menu.addAction("Phase0")
tray.setContextMenu(menu)
def activated(reason):
    print(f"TRAY_ACTIVATED {reason}", file=LOG)
tray.activated.connect(activated)
tray.show()
print("TRAY_SHOW", tray.isVisible(), "SUPPORTS", QSystemTrayIcon.isSystemTrayAvailable(), file=LOG)
QTimer.singleShot(30000, app.quit)
sys.exit(app.exec())
