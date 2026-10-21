import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
m = VirtualMouse()
try:
    m.move_rel(-10000, -10000)
    time.sleep(0.4)
    m.move_rel(500, 72)
    time.sleep(0.5)
    print('click outside pet')
    m.click()
    time.sleep(0.8)
    m.move_rel(-10000, -10000)
    time.sleep(0.3)
    m.move_rel(720, 846)
    time.sleep(0.6)
    print('click pet head', 720, 846)
    m.click()
    time.sleep(0.8)
finally:
    m.close()
