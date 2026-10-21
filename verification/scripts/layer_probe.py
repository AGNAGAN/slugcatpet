import ctypes, os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, Qt
import shiboken6

app = QApplication(sys.argv)
w = QWidget()
w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
w.resize(200, 200)
w.show()
w.hide()
wh = w.windowHandle()
ptr = shiboken6.getCppPointer(wh)[0]
print("QWindow ptr", hex(ptr), flush=True)
lib = ctypes.CDLL("libLayerShellQtInterface.so.6")
get = getattr(lib, "_ZN12LayerShellQt6Window3getEP7QWindow")
get.argtypes = [ctypes.c_void_p]
get.restype = ctypes.c_void_p
set_anchors = getattr(lib, "_ZN12LayerShellQt6Window10setAnchorsE6QFlagsINS0_6AnchorEE")
set_anchors.argtypes = [ctypes.c_void_p, ctypes.c_int]
set_layer = getattr(lib, "_ZN12LayerShellQt6Window8setLayerENS0_5LayerE")
set_layer.argtypes = [ctypes.c_void_p, ctypes.c_int]
set_kb = getattr(lib, "_ZN12LayerShellQt6Window24setKeyboardInteractivityENS0_21KeyboardInteractivityE")
set_kb.argtypes = [ctypes.c_void_p, ctypes.c_int]
set_zone = getattr(lib, "_ZN12LayerShellQt6Window16setExclusiveZoneEi")
set_zone.argtypes = [ctypes.c_void_p, ctypes.c_int]
lp = get(ptr)
print("LayerShellQt::Window ptr", hex(lp or 0), flush=True)
if not lp:
    sys.exit(2)
set_anchors(lp, 1 | 4)  # top | left
set_layer(lp, 3)        # overlay
set_kb(lp, 0)           # none
set_zone(lp, -1)        # no exclusive zone
w.show()
QTimer.singleShot(1500, app.quit)
sys.exit(app.exec())
