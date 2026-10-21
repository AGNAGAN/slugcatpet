import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QObject, Slot, ClassInfo
from PySide6.QtDBus import QDBusConnection

LOG = open("verification/logs/live/cursor_service.log", "w", buffering=1)

@ClassInfo({"D-Bus Interface": "org.slugcatpet.Phase0"})
class Service(QObject):
    @Slot(int, int)
    def Cursor(self, x, y):
        print(f"CURSOR {x} {y}", file=LOG)
    @Slot(str)
    def Note(self, s):
        print(f"NOTE {s}", file=LOG)

app = QCoreApplication(sys.argv)
bus = QDBusConnection.sessionBus()
print("connected", bus.isConnected(), "service", bus.registerService("org.slugcatpet.Phase0"), file=LOG)
s = Service()
print("object", bus.registerObject("/Phase0", s, QDBusConnection.RegisterOption.ExportAllSlots), file=LOG)
app.exec()
