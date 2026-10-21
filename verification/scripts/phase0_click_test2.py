import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
m = VirtualMouse()
try:
    # 当前大约在 overlay 输入区域内；先移动到目标窗口可见区域（overlay 输入区域外）
    m.move_rel(250, 150)
    time.sleep(0.5)
    print('click target area')
    m.click()
    time.sleep(0.8)
    # 回到屏幕左上角，再进入 overlay 的 300x300 输入区域
    m.move_rel(-10000, -10000)
    time.sleep(0.3)
    m.move_rel(150, 150)
    time.sleep(0.5)
    print('click overlay area')
    m.click()
    time.sleep(0.8)
finally:
    m.close()
