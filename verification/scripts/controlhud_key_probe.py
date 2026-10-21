import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from slugcatpet.ui.panels.controlhud import ControlHud

class Pet:
    variant = "survivor"; name = "Phase0"; controlled = True
class Win:
    def __init__(self): self.pets = [Pet()]
    def stop_control(self): print("STOP")
    def hold_controlled(self): print("HOLD")
app = QApplication(sys.argv)
w = Win(); c = ControlHud(w, w.pets[0]); c.show(); c.setFocus()
QTest.keyPress(c, Qt.Key.Key_D)
print("AFTER_D", c.current_input().x, c.current_input().y, sorted(c._held))
QTest.keyRelease(c, Qt.Key.Key_D)
print("AFTER_RELEASE", c.current_input().x, sorted(c._held))
