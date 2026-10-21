import sys,time
sys.path.insert(0,'verification/scripts')
from uinput_mouse import VirtualMouse
from uinput_keyboard import VirtualKeyboard
X,Y=1707.0,1967.0
m=VirtualMouse(absolute=True); k=VirtualKeyboard()
def move(x,y): m.move_abs(round(x/X*32767),round(y/Y*32767)); time.sleep(0.4)
try:
    move(720,814)
    print('click control'); m.click(); time.sleep(0.8)
    print('press D'); k.key('D',True); time.sleep(2.5)
    print('release D'); k.key('D',False); time.sleep(0.8)
    move(100,75)
    print('click lineedit'); m.click(); time.sleep(0.8)
finally:
    k.close(); m.close()
