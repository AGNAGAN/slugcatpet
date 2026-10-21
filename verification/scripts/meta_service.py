import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QObject, Slot, ClassInfo
from PySide6.QtDBus import QDBusConnection

LOG = open("verification/logs/live/meta_service.log", "w", buffering=1)
@ClassInfo({"D-Bus Interface": "org.slugcatpet.Phase0Meta"})
class Service(QObject):
    @Slot(str)
    def WindowList(self, s):
        print(f"WINDOW_LIST {s}", file=LOG)
    @Slot(str)
    def Note(self, s):
        print(f"NOTE {s}", file=LOG)

app = QCoreApplication(sys.argv)
bus = QDBusConnection.sessionBus()
print("connected", bus.isConnected(), "service", bus.registerService("org.slugcatpet.Phase0Meta"), file=LOG)
s = Service()
print("object", bus.registerObject("/Meta", s, QDBusConnection.RegisterOption.ExportAllSlots), file=LOG)
app.exec()
