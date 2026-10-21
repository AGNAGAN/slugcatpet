import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
m = VirtualMouse()
try:
    # 移到所在屏左上角，再移到目标窗口区域（out of overlay input region）
    m.move_rel(-10000, -10000)
    time.sleep(0.4)
    m.move_rel(700, 500)
    time.sleep(0.4)
    print('click target area')
    m.click()
    time.sleep(0.6)
    # 回到屏幕左上角，再移到 overlay 的 300x300 输入区域内
    m.move_rel(-10000, -10000)
    time.sleep(0.3)
    m.move_rel(150, 150)
    time.sleep(0.4)
    print('click overlay area')
    m.click()
    time.sleep(0.6)
finally:
    m.close()
