import sys, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QObject, Slot
from PySide6.QtDBus import QDBusConnection

class Probe(QObject):
    @Slot(int, int)
    def Cursor(self, x, y):
        print(f"CURSOR {x} {y}", flush=True)
    @Slot(str)
    def Note(self, s):
        print(f"NOTE {s}", flush=True)

app = QCoreApplication(sys.argv)
bus = QDBusConnection.sessionBus()
print("connected", bus.isConnected(), flush=True)
print("register service", bus.registerService("org.slugcatpet.Probe"), flush=True)
p = Probe()
print("register object", bus.registerObject("/Probe", p, QDBusConnection.RegisterOption.ExportAllSlots), flush=True)
app.exec()
