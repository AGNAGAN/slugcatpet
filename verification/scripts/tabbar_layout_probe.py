import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, QRect
from slugcatpet.ui.panels import tabbar as tbmod
from slugcatpet.ui.panels.tabbar import TabBar

class Pet:
    atlas = None
    variant = "survivor"
    name = "Phase0"
    def open_rain(self, *_): pass
    def open_music(self): pass
    def open_settings(self): pass
    def enter_place_mode(self, _): return True
    def has_items(self): return False
    def enter_remove_mode(self): pass
    def clear_all_items(self): pass

app = QApplication(sys.argv)
tbmod.item_kinds = lambda: []
overlay = QWidget(); overlay.resize(1707, 1067)
tab = TabBar(Pet(), app, {})
tab.setParent(overlay)
tab.setWindowFlags(Qt.WindowType.Widget)
tab._screen = QRect(0, 0, 1707, 1067)
tab._edge_x = 600
tab._y = 100
tab.setGeometry(600, 100, 24, 48)
tab.show()
print("COLLAPSED", tab.geometry(), tab.expanded)
tab.toggle()
QTimer.singleShot(300, lambda: (print("EXPANDED", tab.geometry(), tab.expanded, "panel", tab._panel.geometry()), app.quit()))
app.exec()
