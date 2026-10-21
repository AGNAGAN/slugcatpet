import time

from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT]}, name="slugcatpet-escape-long")
time.sleep(0.3)
# The app warps back at 40 Hz; keep moving until the pointer crosses onto eDP-1.
for _ in range(240):
    ui.write(e.EV_REL, e.REL_Y, -120)
    ui.syn()
    time.sleep(0.008)
time.sleep(0.8)
ui.close()
