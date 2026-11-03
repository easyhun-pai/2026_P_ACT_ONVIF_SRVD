#!/usr/bin/env python3
# pantilt.py(박스의 98줄 원본)와 동일한 초기화/전송/종료 + 방향키.
#   초기화: R -> 1s -> S -> 1s   (원본 main() 그대로)
#   구동  : 방향키 = 그 방향으로 매 틱 STEP씩 램프하며 T 연속 전송 (스윕과 동일)
#   종료  : R (토크 해제, 원본 finally 그대로)
#   → ← : pan +/-    ↑ ↓ : tilt +/-    space : 정지    q : 종료
# 제한: pan -135~135도, tilt 0~90도 (경계 자동정지)
import time, math, serial, sys, os, threading, termios, tty, select

PORT_PAN = "/dev/ttyAMA0"
PORT_TILT = "/dev/ttyAMA2"
BAUD = 115200
INTERVAL_SEC = 0.01
PAN_STEP_RAD  = 0.05
TILT_STEP_RAD = 0.2

D2R = math.pi/180.0
PAN_MIN, PAN_MAX  = -135*D2R, 135*D2R
TILT_MIN, TILT_MAX = 0.0, math.pi/2

def send(ser, cmd):
    ser.write((cmd + "\n").encode("ascii"))
    ser.flush()

val_pan, val_tilt = 0.0, 0.0
dir_pan, dir_tilt = 0, 0
running = True

def tx_loop(pan, tilt):
    global val_pan, val_tilt, dir_pan, dir_tilt
    while running:
        if dir_pan:
            val_pan += dir_pan * PAN_STEP_RAD
            if val_pan >= PAN_MAX: val_pan = PAN_MAX; dir_pan = 0
            if val_pan <= PAN_MIN: val_pan = PAN_MIN; dir_pan = 0
            send(pan, f"T{val_pan:.4f}")
        if dir_tilt:
            val_tilt += dir_tilt * TILT_STEP_RAD
            if val_tilt >= TILT_MAX: val_tilt = TILT_MAX; dir_tilt = 0
            if val_tilt <= TILT_MIN: val_tilt = TILT_MIN; dir_tilt = 0
            send(tilt, f"T{val_tilt:.4f}")
        time.sleep(INTERVAL_SEC)

def main():
    global dir_pan, dir_tilt, running
    pan = serial.Serial(PORT_PAN, BAUD, timeout=1)
    tilt = serial.Serial(PORT_TILT, BAUD, timeout=1)
    # ===== pantilt.py 원본 초기화 그대로 =====
    print("init: R ...")
    send(pan, "R"); send(tilt, "R")
    time.sleep(1.0)
    print("init: S ...")
    send(pan, "S"); send(tilt, "S")
    time.sleep(1.0)
    th = threading.Thread(target=tx_loop, args=(pan, tilt), daemon=True); th.start()
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    print("→←=pan  ↑↓=tilt  space=정지  q=종료  (pan ±135도 / tilt 0~90도)")
    try:
        tty.setcbreak(fd)
        while True:
            r,_,_ = select.select([sys.stdin], [], [], 0.1)
            if r:
                ch = os.read(fd, 3)
                if ch in (b'q', b'\x03'): break
                elif ch == b'\x1b[C': dir_pan  = +1
                elif ch == b'\x1b[D': dir_pan  = -1
                elif ch == b'\x1b[A': dir_tilt = +1
                elif ch == b'\x1b[B': dir_tilt = -1
                elif ch == b' ': dir_pan = 0; dir_tilt = 0
            sys.stdout.write("\rpan=%+7.1f도(%s)  tilt=%+6.1f도(%s)   " % (
                val_pan/D2R, {1:'→',-1:'←',0:'·'}[dir_pan],
                val_tilt/D2R, {1:'↑',-1:'↓',0:'·'}[dir_tilt]))
            sys.stdout.flush()
    finally:
        running = False; time.sleep(0.05)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        # ===== pantilt.py 원본 종료 그대로 (R = 토크해제) =====
        try: send(pan, "R"); pan.close()
        except Exception: pass
        try: send(tilt, "R"); tilt.close()
        except Exception: pass
        print("\nbye (R sent, torque released)")

if __name__ == "__main__":
    main()
