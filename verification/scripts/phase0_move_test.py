import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
m = VirtualMouse()
try:
    m.move_rel(-10000, -10000)
    time.sleep(0.5)
    m.move_rel(700, 500)
    time.sleep(0.5)
    print('moved to target attempt')
finally:
    m.close()
