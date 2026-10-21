import ctypes, ctypes.util, time
x11 = ctypes.CDLL(ctypes.util.find_library('X11'))
xtst = ctypes.CDLL(ctypes.util.find_library('Xtst'))
x11.XOpenDisplay.restype = ctypes.c_void_p
d = x11.XOpenDisplay(None)
print('display', hex(d) if d else None)
if d:
    xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
    print('move1', xtst.XTestFakeMotionEvent(d, -1, 1400, 1700, 0))
    x11.XFlush(d)
    time.sleep(0.5)
    print('move2', xtst.XTestFakeMotionEvent(d, -1, 1371, 1634, 0))
    x11.XFlush(d)
