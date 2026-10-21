import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, QObject, Slot, ClassInfo, QRect
from PySide6.QtGui import QRegion, QGuiApplication
from PySide6.QtDBus import QDBusConnection

from slugcatpet.ui.panels import tabbar as tbmod
from slugcatpet.ui.panels.tabbar import TabBar
from slugcatpet.ui.panels.controlhud import ControlHud

LOG = open("verification/logs/live/phase0_panels.log", "w", buffering=1)

class FakePet:
    def __init__(self):
        self.atlas = None
        self.variant = "survivor"
        self.name = "Phase0"
        self.controlled = True
    def open_rain(self, *_): print("PET open_rain", file=LOG)
    def open_music(self): print("PET open_music", file=LOG)
    def open_settings(self): print("PET open_settings", file=LOG)
    def enter_place_mode(self, kind): print(f"PET place {kind}", file=LOG); return True
    def has_items(self): return False
    def enter_remove_mode(self): print("PET remove_mode", file=LOG)
    def clear_all_items(self): print("PET clear_all", file=LOG)

class LoggedControlHud(ControlHud):
    def keyPressEvent(self, e):
        print(f"CTRL_KEY {e.key()}", file=LOG)
        super().keyPressEvent(e)

class FakeWindow:
    def __init__(self, pet):
        self.pets = [pet]
        self.held = 0
    def stop_control(self): print("WIN stop_control", file=LOG)
    def hold_controlled(self): self.held += 1; print("WIN hold", file=LOG)

@ClassInfo({"D-Bus Interface": "org.slugcatpet.Phase0Panels"})
class CursorSvc(QObject):
    @Slot(int, int)
    def Cursor(self, x, y):
        print(f"CURSOR {x} {y}", file=LOG)
    @Slot()
    def Report(self):
        try:
            print(f"REPORT TAB {tab.geometry()} EXPANDED {tab.expanded} CTRL {ctrl.geometry()} FOCUS {type(QApplication.focusWidget()).__name__} HELD {sorted(ctrl._held)} X {ctrl.current_input().x}", file=LOG)
        except Exception as e:
            print(f"REPORT_ERR {e!r}", file=LOG)

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("phase0-panels")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1707, 1067)
        self.show()
        QTimer.singleShot(800, self.set_full_input)

    def mousePressEvent(self, e):
        print(f"OVERLAY_CLICK {e.position().x():.0f} {e.position().y():.0f}", file=LOG)
        super().mousePressEvent(e)

    def set_full_input(self):
        r = QRegion(0, 0, self.width(), self.height())
        self.windowHandle().setMask(r)
        self.windowHandle().requestUpdate()
        self.update()
        print(f"OVERLAY_FULL_INPUT {r.boundingRect()} DPR {self.devicePixelRatioF()}", file=LOG)

app = QApplication(sys.argv)
bus = QDBusConnection.sessionBus()
print("SERVICE", bus.registerService("org.slugcatpet.Phase0Panels"), file=LOG)
svc = CursorSvc()
print("OBJECT", bus.registerObject("/Panels", svc, QDBusConnection.RegisterOption.ExportAllSlots), file=LOG)
pet = FakePet()
win = FakeWindow(pet)

# 只保留真实 TabBar 的按钮/布局，不依赖真实 item atlas。
tbmod.item_kinds = lambda: []
tab = TabBar(pet, app, {})
tab.setParent(None)
tab.setWindowFlags(Qt.WindowType.Widget)
tab._screen = QRect(0, 0, 1707, 1067)
tab._edge_x = 600
tab._y = 100
tab.setGeometry(600, tab._y, 24, 48)
tab.show()

ctrl = LoggedControlHud(win, pet)
ctrl.setParent(None)
ctrl.setWindowFlags(Qt.WindowType.Widget)
ctrl.move(180, 220)
ctrl.show()

overlay = Overlay()
# 关键：把真实面板 reparent 到 overlay
tab.setParent(overlay)
ctrl.setParent(overlay)
tab.move(600, tab._y)
ctrl.move(180, 220)
tab.show(); ctrl.show()
tab.raise_(); ctrl.raise_()

QTimer.singleShot(1000, lambda: print(f"TAB_GEO {tab.geometry()} ARROW {tab._arrow.geometry()} EXPANDED {tab.expanded}", file=LOG))
QTimer.singleShot(1200, lambda: print(f"CTRL_GEO {ctrl.geometry()} FOCUS {type(QApplication.focusWidget()).__name__}", file=LOG))
QTimer.singleShot(8000, lambda: print(f"TAB_AFTER_CLICK {tab.geometry()} EXPANDED {tab.expanded}", file=LOG))
QTimer.singleShot(8200, lambda: print(f"CTRL_AFTER_INPUT x={ctrl.current_input().x} y={ctrl.current_input().y} held={sorted(ctrl._held)}", file=LOG))
QTimer.singleShot(8400, lambda: print(f"FOCUS_AFTER {type(QApplication.focusWidget()).__name__}", file=LOG))
QTimer.singleShot(60000, app.quit)
sys.exit(app.exec())
