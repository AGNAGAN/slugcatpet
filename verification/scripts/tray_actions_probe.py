import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QTimer
LOG = open("verification/logs/live/tray_actions.log", "w", buffering=1)
app = QApplication(sys.argv)
tray = QSystemTrayIcon(QIcon.fromTheme("applications-system"))
tray.setToolTip("slugcatpet phase0 tray actions")
menu = QMenu()
act_settings = QAction("Settings", menu)
act_music = QAction("Music", menu)
act_quit = QAction("Quit", menu)
for a in (act_settings, act_music, act_quit): menu.addAction(a)
tray.setContextMenu(menu)
act_settings.triggered.connect(lambda: print("ACTION settings", file=LOG))
act_music.triggered.connect(lambda: print("ACTION music", file=LOG))
act_quit.triggered.connect(lambda: print("ACTION quit", file=LOG))
def activated(reason):
    print(f"TRAY_ACTIVATED {reason}", file=LOG)
    act_settings.trigger()
tray.activated.connect(activated)
tray.show()
print("TRAY_SHOW", tray.isVisible(), "SUPPORTS", QSystemTrayIcon.isSystemTrayAvailable(), file=LOG)
QTimer.singleShot(15000, app.quit)
sys.exit(app.exec())
