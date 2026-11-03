#!/usr/bin/env python3
# =====================================================================
# 연속·부드러운 PTZ 컨트롤러 (onvif OFF 상태, 직접 시리얼)
#  - 절대 T값을 작은 스텝으로 등속 연속 스트리밍 (엔코더 안읽음/ wrap계산 없음)
#  - arm(R,S)는 시작에 1번만 -> 이후 R 없음 -> 팍팍 안 튐
#  - 위치는 명령 기준 dead-reckoning (시작 0,0 가정)
#
# 사용:
#   sudo python3 ptz_cont.py               # 대화형
#     > 0 30          pan=0도 tilt=30도 부드럽게 이동+홀드
#     > 45 60
#     > sweep pan     pan 범위 왕복(연속)
#     > sweep tilt
#     > stop          스윕 정지(현위치 홀드)
#     > off           토크 해제(limp)
#     > q             종료
#   sudo python3 ptz_cont.py 0 30          # 한번 이동 후 홀드
# 속도조절: STEP(작게=느림) / INTERVAL(작게=촘촘)
# =====================================================================
import sys, time, math, serial, threading

PORT_PAN="/dev/ttyAMA0"; PORT_TILT="/dev/ttyAMA2"; BAUD=115200
INTERVAL = 0.01        # 스트림 간격(초)
STEP     = 0.02        # rad/틱 (0.02*100=2rad/s). 부드럽게. 필요시 0.01~0.04
D2R=math.pi/180.0
PAN_MIN,PAN_MAX   = -135*D2R, 135*D2R
TILT_MIN,TILT_MAX =    0*D2R,  90*D2R

def clamp(v,lo,hi): return max(lo,min(hi,v))

class Axis:
    def __init__(self, port, lo, hi, start=0.0):
        self.s=serial.Serial(port,BAUD,timeout=1); time.sleep(0.2)
        self.lo=lo; self.hi=hi; self.cur=start
    def arm(self):
        self.s.write(b"R\n"); self.s.flush(); time.sleep(2.5)
        self.s.write(b"S\n"); self.s.flush(); time.sleep(1.5)
    def send(self,v):
        self.s.write(("T%.4f\n"%v).encode()); self.s.flush()
    def off(self):
        self.s.write(b"R\n"); self.s.flush(); time.sleep(0.3)

def glide(axes, targets):
    """여러 축 동시에 등속 소스텝으로 target 도달 (연속 스트림, 부드러움)"""
    targets=[clamp(t,a.lo,a.hi) for a,t in zip(axes,targets)]
    while True:
        done=True
        for a,t in zip(axes,targets):
            d=t-a.cur
            if abs(d)<=STEP:
                a.cur=t
            else:
                a.cur+=math.copysign(STEP,d); done=False
            a.send(a.cur)
        time.sleep(INTERVAL)
        if done: break

_sweep=False
def sweep_loop(ax):
    global _sweep; _sweep=True
    v=ax.cur; d=STEP
    while _sweep:
        v+=d
        if v>=ax.hi: v=ax.hi; d=-STEP
        elif v<=ax.lo: v=ax.lo; d=STEP
        ax.cur=v; ax.send(v); time.sleep(INTERVAL)

def main():
    global _sweep
    pan=Axis(PORT_PAN,PAN_MIN,PAN_MAX,0.0)
    tilt=Axis(PORT_TILT,TILT_MIN,TILT_MAX,0.0)
    # 토크 필요 -> 기본 S arm (R 리셋없이=팍팍 최소). --arm: R+S, --no-arm: 생략
    if "--no-arm" not in sys.argv:
        if "--arm" in sys.argv:
            print("arming (R,S) once ..."); pan.arm(); tilt.arm()
        else:
            print("arming (S) ..."); pan.s.write(b"S\n"); pan.s.flush(); tilt.s.write(b"S\n"); tilt.s.flush(); time.sleep(1.5)
    print("ready (연속 T 스트림). cur=pan0/tilt0 가정")
    nums=[a for a in sys.argv[1:] if not a.startswith('-')]
    if len(nums)>=2:
        glide([pan,tilt],[float(nums[0])*D2R,float(nums[1])*D2R])
        print("held pan=%s tilt=%s (torque 유지)"%(nums[0],nums[1])); return
    print("명령: '<pan도> <tilt도>' | 'sweep pan|tilt' | 'stop' | 'off' | 'q'")
    for line in sys.stdin:
        c=line.strip().split()
        if not c: continue
        if c[0]=='q': break
        if c[0]=='off': _sweep=False; time.sleep(0.05); pan.off(); tilt.off(); print("disarmed(limp)"); continue
        if c[0]=='stop': _sweep=False; time.sleep(0.05); print("stop(hold)"); continue
        if c[0]=='sweep' and len(c)>1:
            _sweep=False; time.sleep(0.05)
            ax=pan if c[1]=='pan' else tilt
            threading.Thread(target=sweep_loop,args=(ax,),daemon=True).start()
            print("sweeping %s"%c[1]); continue
        try:
            glide([pan,tilt],[float(c[0])*D2R,float(c[1])*D2R]); print("held %s %s"%(c[0],c[1]))
        except Exception as e:
            print("입력오류:",e)
    print("bye (torque 유지; off로 해제)")

if __name__=="__main__": main()
