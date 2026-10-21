import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from slugcatpet.platform.appid import set_desktop_file_name
from slugcatpet.window import PetWindow

LOG = open('verification/logs/live/phase1_backend.log', 'w', buffering=1)
def log(*a): print(*a, file=LOG)

class ProbePet(PetWindow):
    def mousePressEvent(self, e):
        log('PET_CLICK', round(e.position().x()), round(e.position().y()))
        super().mousePressEvent(e)

class Target(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('phase1-target')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet('background:#205080;')
        self.resize(1440, 900)
        self.setScreen(QGuiApplication.screens()[0])
        self.show()
    def mousePressEvent(self, e):
        log('TARGET_CLICK', round(e.position().x()), round(e.position().y()))

app = QApplication(sys.argv)
set_desktop_file_name()
target = Target()
pet = ProbePet(params={"seed": 12345})
pet.show()

def sample():
    p = pet.pets[0]
    b = p.body
    log('PET_GEO', pet.geometry(), 'SCREEN', pet.screen().name(), 'DPR', pet.devicePixelRatioF())
    log('BODY', round(b.chunk0.x * pet._scale), round(b.chunk0.y * pet._scale))
    log('HEAD', round(p.gfx.head.x * pet._scale), round(p.gfx.head.y * pet._scale))
    log('MASK', pet.windowHandle().mask().boundingRect())
    log('ORIGIN', pet._backend.overlay_origin(), 'CURSOR', pet._backend.cursor_global())
    pet.freeze('user')
QTimer.singleShot(1500, sample)

def end():
    log('END')
    app.quit()
QTimer.singleShot(9000, end)
sys.exit(app.exec())
