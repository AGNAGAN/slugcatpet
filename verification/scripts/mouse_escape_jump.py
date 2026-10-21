import time
from evdev import UInput, ecodes as e

ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT]}, name="slugcatpet-escape-jump")
time.sleep(0.4)
# One large upward jump from HDMI-A-1 onto eDP-1.
ui.write(e.EV_REL, e.REL_Y, -3000)
ui.write(e.EV_REL, e.REL_X, -100)
ui.syn()
time.sleep(1.0)
ui.close()
