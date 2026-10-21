import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
# virtual desktop: eDP 1440x900 at (0,0), HDMI 1707x1067 at (0,900)
X, Y = 1707.0, 1967.0
m = VirtualMouse(absolute=True)
def move(x, y):
    m.move_abs(round(x / X * 32767), round(y / Y * 32767))
    time.sleep(0.5)
try:
    move(500, 100)
    print('click outside pet')
    m.click(); time.sleep(0.8)
    move(720, 846)
    print('click pet')
    m.click(); time.sleep(0.8)
    move(1310, 360)
    print('click tab arrow')
    m.click(); time.sleep(0.8)
finally:
    m.close()
