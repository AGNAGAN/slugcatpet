import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
dx, dy = int(sys.argv[1]), int(sys.argv[2])
m = VirtualMouse()
try:
    m.move_rel(dx, dy)
    time.sleep(0.4)
    print('sent', dx, dy)
finally:
    m.close()
