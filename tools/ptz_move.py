#!/usr/bin/env python3
# =====================================================================
# 수동 PTZ 이동 (onvif 꺼진 상태에서 직접 시리얼 제어)
#
# 사용법:
#   sudo python3 ptz_move.py                 # 아래 TARGET_*_DEG 값으로 이동
#   sudo python3 ptz_move.py 0 30            # pan=0도, tilt=30도 로 이동
#   sudo python3 ptz_move.py 45 60 --pan-only
#   sudo python3 ptz_move.py --sweep-pan     # pan MIN<->MAX 왕복 1회(테스트)
#   sudo python3 ptz_move.py --disarm        # 양축 토크 해제(limp)만
#
# 안전:
#  - 항상 wrapd 최단경로로 램프 -> 한 번에 최대 180도, 2바퀴 스핀 불가
#  - 스펙 범위로 클램프 (pan +-135, tilt 0~90)
#  - 이상발산 감지시 즉시 R(정지)
# =====================================================================
import sys, time, math, re, serial

PORT_PAN  = "/dev/ttyAMA0"
PORT_TILT = "/dev/ttyAMA2"
BAUD      = 115200

# ===== 원하는 각도 (도) — 인자 없으면 이 값 사용 =====
TARGET_PAN_DEG  = 0.0
TARGET_TILT_DEG = 30.0

# ===== 램프/범위 파라미터 =====
STEP_RAD    = 0.02          # 램프 스텝(작을수록 부드럽고 안전)
INTERVAL    = 0.03          # 스텝 간격(초)
SETTLE      = 0.8
DIVERGE_ABORT = 1.2         # 명령-실제 오차 이 이상이면 발산으로 보고 정지
PAN_LIM_DEG   = 135.0
TILT_MIN_DEG  = 0.0
TILT_MAX_DEG  = 90.0
D2R = math.pi/180.0

def wrapd(x): return math.remainder(x, 2*math.pi)
def openp(p):
    s=serial.Serial(p,BAUD,timeout=0.1); time.sleep(0.2); s.reset_input_buffer(); return s
def rd(s,t):
    e=time.time()+t; b=b""
    while time.time()<e:
        n=s.in_waiting
        if n: b+=s.read(n)
        else: time.sleep(0.005)
    return b.decode('utf-8','replace')
def curv(t):
    c=re.findall(r'Current angle:\s*(-?\d+\.?\d*)',t); return float(c[-1]) if c else None

def arm(s,name):
    print(f"[{name}] R(align)"); s.write(b"R\n"); s.flush(); rd(s,2.8)
    print(f"[{name}] S(arm)");   s.write(b"S\n"); s.flush(); rd(s,1.5)

def disarm(s,name):
    s.write(b"R\n"); s.flush(); rd(s,0.4)
    print(f"[{name}] disarmed(limp)")

def probe(s,target):
    # 단발T는 이 MCU를 구동 안함(안전) -> 현재위치 읽기용
    s.write(f"T{target:.3f}\n".encode()); s.flush()
    return curv(rd(s,1.5))

def ramp(s,name,target_rad):
    c0=probe(s,target_rad)
    if c0 is None:
        print(f"[{name}] 현재위치 못읽음 -> 안전위해 구동 생략(R)"); disarm(s,name); return False
    cur=wrapd(c0); need=wrapd(target_rad-cur)
    print(f"[{name}] cur={cur:+.3f} target={target_rad:+.3f} need={need:+.3f}rad ({need/D2R:+.1f}도, 최단경로)")
    step = STEP_RAD if need>0 else -STEP_RAD
    cmd=cur
    while abs(wrapd(target_rad-cmd))>STEP_RAD:
        cmd+=step
        s.write(f"T{cmd:.4f}\n".encode()); s.flush()
        rc=curv(rd(s,0.005) or "")
        time.sleep(INTERVAL)
        if rc is not None and abs(wrapd(wrapd(rc)-cmd))>DIVERGE_ABORT:
            print(f"[{name}] 발산 cmd={cmd:+.3f} cur={wrapd(rc):+.3f} -> ABORT+R"); disarm(s,name); return False
    s.write(f"T{target_rad:.4f}\n".encode()); s.flush()
    time.sleep(SETTLE); fin=curv(rd(s,0.6))
    print(f"[{name}] 도달 target={target_rad:+.3f} fin_cur={fin} (torque 유지)")
    return True

def sweep_pan(s):
    lo,hi=-PAN_LIM_DEG*D2R, PAN_LIM_DEG*D2R
    print("[PAN] sweep lo->hi->lo")
    v=lo
    while v<=hi: s.write(f"T{v:.4f}\n".encode()); s.flush(); time.sleep(INTERVAL); v+=0.05
    v=hi
    while v>=lo: s.write(f"T{v:.4f}\n".encode()); s.flush(); time.sleep(INTERVAL); v-=0.05

def clamp(v,lo,hi): return max(lo,min(hi,v))

def main():
    args=[a for a in sys.argv[1:]]
    pan_only  = "--pan-only"  in args
    tilt_only = "--tilt-only" in args
    if "--disarm" in args:
        sp=openp(PORT_PAN); st=openp(PORT_TILT); disarm(sp,"PAN"); disarm(st,"TILT"); return
    if "--sweep-pan" in args:
        sp=openp(PORT_PAN); arm(sp,"PAN"); sweep_pan(sp); return
    nums=[a for a in args if not a.startswith("--")]
    pdeg = float(nums[0]) if len(nums)>=1 else TARGET_PAN_DEG
    tdeg = float(nums[1]) if len(nums)>=2 else TARGET_TILT_DEG
    pan  = clamp(pdeg,-PAN_LIM_DEG,PAN_LIM_DEG)*D2R
    tilt = clamp(tdeg,TILT_MIN_DEG,TILT_MAX_DEG)*D2R
    print(f"목표 pan={pdeg}도({pan:+.3f}) tilt={tdeg}도({tilt:+.3f})")
    if not tilt_only:
        sp=openp(PORT_PAN);  arm(sp,"PAN");  ramp(sp,"PAN",pan);   sp.close()
    if not pan_only:
        st=openp(PORT_TILT); arm(st,"TILT"); ramp(st,"TILT",tilt); st.close()
    print("완료.")

if __name__=="__main__":
    main()
