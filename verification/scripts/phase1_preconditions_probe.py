import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from slugcatpet.window import PetWindow
from slugcatpet.ui.panels.tabbar import TabBar
from slugcatpet.ui.panels.hud import HudPanel
from slugcatpet.ui.panels.controlhud import ControlHud
from slugcatpet.ui.raintimer.dial import RainDial
from slugcatpet.world.raintimer import RainTimer

LOG = open('verification/logs/live/phase1_preconditions.log', 'w', buffering=1)
def log(*a): print(*a, file=LOG)

class FakeWindow:
    def __init__(self, pet):
        self.pets = [pet]
    def stop_control(self):
        log('FAKE stop_control')
    def hold_controlled(self):
        log('FAKE hold_controlled')

class FakePet:
    variant = 'survivor'
    name = 'Phase1'
    controlled = True
    def __init__(self):
        self.body = SimpleNamespace(energy=1, temper=0, food=1, food_q=1, karma=1, cold=0, sleepiness=0)
        self.personality = 'normal'
        self.hidden = False

app = QApplication(sys.argv)
params = {}
pet = PetWindow(params=params)
pet.show()
log('PET_WAYLAND', pet._wayland, 'SCREEN', pet.screen().name(), 'DPR', pet.devicePixelRatioF(), 'GEO', pet.geometry())

tab = TabBar(pet, app, params, parent=pet, embedded=True)
pet._tab = tab
tab.show()

hud = HudPanel(pet, params, parent=pet, embedded=True)
pet._hud = hud
hud.toggle_visible()

rain_timer = RainTimer({})
dial = RainDial(rain_timer, pet.atlas, {}, muted=lambda: True, context=lambda: None, parent=pet, embedded=True)
pet._rain_dial = dial

fake_pet = FakePet()
fake_window = FakeWindow(fake_pet)
ctrl = ControlHud(fake_window, fake_pet, parent=pet, embedded=True)
pet._control_hud = ctrl
ctrl.show()

def report0():
    log('HANDLE', pet.windowHandle() is not None)
    log('MASK', pet.windowHandle().mask().boundingRect() if pet.windowHandle() else None)
    log('TAB_SCREEN', tab._screen, 'TAB_GEO', tab.geometry(), 'TAB_PARENT', tab.parentWidget() is pet)
    log('HUD_GEO', hud.geometry(), 'HUD_PARENT', hud.parentWidget() is pet, 'HUD_VIS', hud.isVisible())
    log('DIAL_GEO', dial.geometry(), 'DIAL_PARENT', dial.parentWidget() is pet, 'DIAL_VIS', dial.isVisible())
    log('CTRL_GEO', ctrl.geometry(), 'CTRL_PARENT', ctrl.parentWidget() is pet, 'CTRL_FOCUS', QApplication.focusWidget() is ctrl, 'PAUSED', ctrl._paused)
    region = pet._build_input_region()
    log('REGION_BOUNDS', region.boundingRect(), 'FULL', region == pet.rect())
    pts = []
    for p in pet.pets:
        g = p.gfx
        pts.append((round(g.head.x * pet._scale), round(g.head.y * pet._scale)))
    log('PET_HEAD_POINTS', pts, 'CONTAINS', [region.contains(SimpleNamespace(x=x,y=y) if False else None) for x in []])
    tab.toggle()
    QTimer.singleShot(250, report1)

def report1():
    log('TAB_EXPANDED', tab.expanded, 'TAB_GEO', tab.geometry(), 'PANEL', tab._panel.geometry(), 'ARROW', tab._arrow.geometry())
    ctrl.setFocus()
    app.processEvents()
    log('FOCUS_AFTER_SET', QApplication.focusWidget() is ctrl, 'PAUSED', ctrl._paused)
    QTest.keyPress(ctrl, Qt.Key.Key_D)
    app.processEvents()
    inp = ctrl.current_input()
    log('KEY_D', sorted(ctrl._held), 'X', inp.x, 'Y', inp.y, 'PAUSED', ctrl._paused)
    QTest.keyRelease(ctrl, Qt.Key.Key_D)
    app.processEvents()
    log('KEY_RELEASE', sorted(ctrl._held), 'X', ctrl.current_input().x)
    ctrl.clearFocus()
    app.processEvents()
    log('AFTER_CLEAR_FOCUS', QApplication.focusWidget(), 'PAUSED', ctrl._paused, 'X', ctrl.current_input().x)
    ctrl.setFocus()
    app.processEvents()
    log('AFTER_REFOCUS', QApplication.focusWidget() is ctrl, 'PAUSED', ctrl._paused)
    QTimer.singleShot(300, finish)

def finish():
    log('MASK_FINAL', pet.windowHandle().mask().boundingRect())
    pet._shutting_down = True
    app.quit()

QTimer.singleShot(800, report0)
QTimer.singleShot(6000, app.quit)
sys.exit(app.exec())
