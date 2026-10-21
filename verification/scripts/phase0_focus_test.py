import sys, time
sys.path.insert(0, 'verification/scripts')
from uinput_mouse import VirtualMouse
from uinput_keyboard import VirtualKeyboard
m = VirtualMouse(); k = VirtualKeyboard()
try:
    # 移到屏幕左上角，再点击 overlay 内的 QLineEdit（global 约 100,1000）
    m.move_rel(-10000, -10000); time.sleep(0.3)
    m.move_rel(100, 100); time.sleep(0.4)
    print('click line edit')
    m.click(); time.sleep(0.5)
    print('type A')
    k.tap('A'); time.sleep(0.5)
finally:
    k.close(); m.close()
