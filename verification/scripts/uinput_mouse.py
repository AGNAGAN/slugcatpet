"""Minimal uinput virtual mouse for Phase 0 input tests."""
from __future__ import annotations
import ctypes, fcntl, os, struct, time

# linux/uinput.h
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405c5503
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566
UI_SET_ABSBIT = 0x40045567
UI_SET_PROPBIT = 0x4004556e

EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
REL_X, REL_Y = 0, 1
ABS_X, ABS_Y = 0, 1
BTN_LEFT, BTN_RIGHT = 0x110, 0x111
SYN_REPORT = 0

class input_id(ctypes.Structure):
    _fields_ = [("bustype", ctypes.c_uint16), ("vendor", ctypes.c_uint16),
                ("product", ctypes.c_uint16), ("version", ctypes.c_uint16)]

class uinput_setup(ctypes.Structure):
    _fields_ = [("id", input_id), ("name", ctypes.c_char * 80), ("ff_effects_max", ctypes.c_uint32)]

class input_absinfo(ctypes.Structure):
    _fields_ = [("value", ctypes.c_int32), ("minimum", ctypes.c_int32),
                ("maximum", ctypes.c_int32), ("fuzz", ctypes.c_int32),
                ("flat", ctypes.c_int32), ("resolution", ctypes.c_int32)]

class uinput_abs_setup(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("absinfo", input_absinfo)]

def _ev(type_, code, value):
    return struct.pack("<qqHHi", 0, 0, type_, code, value)

class VirtualMouse:
    def __init__(self, absolute=False, name="slugcatpet-phase0-mouse"):
        self.absolute = absolute
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for ev in (EV_SYN, EV_KEY, EV_REL if not absolute else EV_ABS):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        for key in (BTN_LEFT, BTN_RIGHT):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, key)
        if absolute:
            fcntl.ioctl(self.fd, UI_SET_PROPBIT, 0)  # INPUT_PROP_POINTER
            for axis in (ABS_X, ABS_Y):
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, axis)
                setup = uinput_abs_setup(axis, input_absinfo(0, 0, 32767, 0, 0, 0))
                buf = ctypes.create_string_buffer(ctypes.sizeof(setup))
                ctypes.memmove(buf, ctypes.byref(setup), ctypes.sizeof(setup))
                fcntl.ioctl(self.fd, 0x401c5504, buf)  # UI_ABS_SETUP
        else:
            for axis in (REL_X, REL_Y):
                fcntl.ioctl(self.fd, UI_SET_RELBIT, axis)
        setup = uinput_setup()
        setup.id.bustype = 0x03  # BUS_USB
        setup.id.vendor = 0x1209
        setup.id.product = 0x0001
        setup.id.version = 1
        setup.name = name.encode()[:79]
        buf = ctypes.create_string_buffer(ctypes.sizeof(setup))
        ctypes.memmove(buf, ctypes.byref(setup), ctypes.sizeof(setup))
        fcntl.ioctl(self.fd, UI_DEV_SETUP, buf)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self._created = True
        time.sleep(0.4)  # let the compositor pick up the device

    def _write(self, *events):
        os.write(self.fd, b"".join(events))
        os.write(self.fd, _ev(EV_SYN, SYN_REPORT, 0))

    def move_rel(self, dx, dy, steps=1):
        for i in range(steps):
            self._write(_ev(EV_REL, REL_X, int(dx)), _ev(EV_REL, REL_Y, int(dy)))
            time.sleep(0.01)

    def move_abs(self, x, y):
        self._write(_ev(EV_ABS, ABS_X, int(x)), _ev(EV_ABS, ABS_Y, int(y)))

    def click(self, button=BTN_LEFT):
        self._write(_ev(EV_KEY, button, 1))
        time.sleep(0.05)
        self._write(_ev(EV_KEY, button, 0))
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

if __name__ == "__main__":
    m = VirtualMouse(absolute=False)
    try:
        m.move_rel(-10000, -10000)
        time.sleep(0.2)
        m.move_rel(400, 300)
        time.sleep(0.2)
        print("moved")
    finally:
        m.close()
