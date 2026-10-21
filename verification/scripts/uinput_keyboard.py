"""Minimal uinput virtual keyboard for Phase 0 tests."""
from __future__ import annotations
import ctypes, fcntl, os, struct, time

UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405c5503
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565

EV_SYN, EV_KEY = 0, 1
SYN_REPORT = 0
KEY = {
    "ESC": 1, "1": 2, "A": 30, "B": 48, "C": 46, "H": 35, "P": 25, "Q": 16, "X": 45,
    "D": 32, "ENTER": 28, "LEFTCTRL": 29, "LEFTALT": 56, "LEFTSHIFT": 42, "RIGHT": 106,
}

class input_id(ctypes.Structure):
    _fields_ = [("bustype", ctypes.c_uint16), ("vendor", ctypes.c_uint16),
                ("product", ctypes.c_uint16), ("version", ctypes.c_uint16)]

class uinput_setup(ctypes.Structure):
    _fields_ = [("id", input_id), ("name", ctypes.c_char * 80), ("ff_effects_max", ctypes.c_uint32)]

def _ev(type_, code, value):
    return struct.pack("<qqHHi", 0, 0, type_, code, value)

class VirtualKeyboard:
    def __init__(self, name="slugcatpet-phase0-keyboard"):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        for code in KEY.values():
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        setup = uinput_setup()
        setup.id.bustype = 0x03
        setup.id.vendor = 0x1209
        setup.id.product = 0x0002
        setup.id.version = 1
        setup.name = name.encode()[:79]
        buf = ctypes.create_string_buffer(ctypes.sizeof(setup))
        ctypes.memmove(buf, ctypes.byref(setup), ctypes.sizeof(setup))
        fcntl.ioctl(self.fd, UI_DEV_SETUP, buf)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self._created = True
        time.sleep(0.4)

    def _write(self, *events):
        os.write(self.fd, b"".join(events))
        os.write(self.fd, _ev(EV_SYN, SYN_REPORT, 0))

    def key(self, name, down=True):
        code = KEY[name]
        self._write(_ev(EV_KEY, code, 1 if down else 0))

    def tap(self, name, hold=0.04):
        self.key(name, True)
        time.sleep(hold)
        self.key(name, False)
        time.sleep(0.05)

    def chord(self, *names):
        for n in names:
            self.key(n, True)
        time.sleep(0.05)
        for n in reversed(names):
            self.key(n, False)
        time.sleep(0.05)

    def close(self):
        if getattr(self, "_created", False):
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except Exception:
                pass
            self._created = False
        try:
            os.close(self.fd)
        except Exception:
            pass
