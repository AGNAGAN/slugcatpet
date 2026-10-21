import sys,time
sys.path.insert(0,'verification/scripts')
from uinput_mouse import VirtualMouse
X,Y=1707.0,1967.0
m=VirtualMouse(absolute=True)
def move(x,y): m.move_abs(round(x/X*32767),round(y/Y*32767)); time.sleep(0.35)
try:
    move(720,814); print('press'); m.click.__self__  # no
    # manual press/move/release
    import struct
    def ev(t,c,v): return struct.pack('<qqHHi',0,0,t,c,v)
    m._write(ev(1,0x110,1)); time.sleep(0.2)
    move(770,764); move(800,744); time.sleep(0.5)
    m._write(ev(1,0x110,0)); time.sleep(0.5)
    print('drag done')
finally:
    m.close()
