import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
from uinput_keyboard import VirtualKeyboard
m = VirtualMouse(); k = VirtualKeyboard()
try:
    # 点到右侧 TabBar 收起箭头：HDMI 左上角 (0,900)，相对移动到 x~1680,y~1020
    m.move_rel(-10000, -10000); time.sleep(0.3)
    m.move_rel(840, 60); time.sleep(0.4)
    print('click tab arrow')
    m.click(); time.sleep(0.7)
    # 点 ControlHud 面板：本地 (200,240) -> 全局 (200,1140)
    m.move_rel(-10000, -10000); time.sleep(0.3)
    m.move_rel(100, 120); time.sleep(0.4)
    print('click control hud')
    m.click(); time.sleep(0.4)
    print('send Right')
    k.tap('RIGHT'); time.sleep(0.4)
finally:
    k.close(); m.close()
