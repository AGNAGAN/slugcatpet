import time
from evdev import UInput, ecodes as e

ui = UInput(
    {e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT]},
    name="slugcatpet-test-mouse",
)
time.sleep(0.5)
for i in range(100):
    for dx, dy in ((4, 0), (-4, 0)):
        ui.write(e.EV_REL, e.REL_X, dx)
        ui.write(e.EV_REL, e.REL_Y, dy)
        ui.syn()
        time.sleep(0.15)
ui.close()
