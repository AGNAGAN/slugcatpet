import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from slugcatpet.window import PetWindow
from slugcatpet.ui.panels.tabbar import TabBar

LOG = open('verification/logs/live/phase1_mask_click.log', 'w', buffering=1)
def log(*a): print(*a, file=LOG)

class ProbePet(PetWindow):
    def mousePressEvent(self, e):
        log('PET_CLICK', round(e.position().x()), round(e.position().y()))
        super().mousePressEvent(e)

class Target(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('phase1-target')
        self.setStyleSheet('background:#205080;')
        self.resize(1200, 700)
        self.setScreen(QGuiApplication.screens()[0])
        self.show()
    def mousePressEvent(self, e):
        log('TARGET_CLICK', round(e.position().x()), round(e.position().y()))

app = QApplication(sys.argv)
target = Target()
pet = ProbePet(params={})
pet.setWindowTitle('phase1-pet')
pet.show()
tab = TabBar(pet, app, {}, parent=pet, embedded=True)
pet._tab = tab
tab.show()
tab.toggle()
log('START PET_GEO', pet.geometry(), 'SCREEN', pet.screen().name(), 'DPR', pet.devicePixelRatioF())
log('TAB', tab.geometry(), 'EXPANDED', tab.expanded)
log('MASK_START', pet.windowHandle().mask().boundingRect())
QTimer.singleShot(7000, lambda: log('TAB_MID', tab.expanded, 'GEO', tab.geometry()))
def end():
    log('TAB_END', tab.expanded, 'GEO', tab.geometry(), 'MASK_END', pet.windowHandle().mask().boundingRect())
    app.quit()
QTimer.singleShot(9000, end)
sys.exit(app.exec())
