import time
from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT]}, name="slugcatpet-to-hdmi")
time.sleep(0.5)
for _ in range(40):
    ui.write(e.EV_REL, e.REL_Y, 100)
    ui.write(e.EV_REL, e.REL_X, 10)
    ui.syn()
    time.sleep(0.02)
ui.close()
