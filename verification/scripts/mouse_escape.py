import time

from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT]}, name="slugcatpet-escape")
time.sleep(0.4)
# Move far upward, off HDMI-A-1 (y >= 900) onto eDP-1 (y < 900).
for _ in range(30):
    ui.write(e.EV_REL, e.REL_Y, -120)
    ui.syn()
    time.sleep(0.02)
time.sleep(0.5)
# A few horizontal nudges to prove the pointer is still under user control.
for _ in range(4):
    ui.write(e.EV_REL, e.REL_X, 40)
    ui.syn()
    time.sleep(0.08)
ui.close()
