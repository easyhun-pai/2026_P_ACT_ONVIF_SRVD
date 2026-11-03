#!/usr/bin/env python3
import time
import math
import serial

# =========================
# 설정
# =========================
PORT_PAN = "/dev/ttyAMA0"   # PAN 포트
PORT_TILT = "/dev/ttyAMA2"  # TILT 포트
BAUD = 115200
INTERVAL_SEC = 0.01          # 전송 간격 (초)

PAN_MIN = -2.8              # rad
PAN_MAX =  2.8               # rad
PAN_STEP_RAD = 0.05          # rad (예: 0.05rad ≈ 2.86도)

TILT_MAX = math.pi / 2       # rad (90도)
TILT_STEP_RAD = 0.2        # rad

def send(ser, cmd: str):
    ser.write((cmd + "\n").encode("ascii"))
    ser.flush()

def sweep_pan_once(ser_pan):
    """PAN을 MIN→MAX→MIN 한 번 왕복"""
    # 올림
    val = PAN_MIN
    while val <= PAN_MAX + 1e-12:
        send(ser_pan, f"T{val:.4f}")
        time.sleep(INTERVAL_SEC)
        val += PAN_STEP_RAD
    # 내림
    val = PAN_MAX - PAN_STEP_RAD
    while val >= PAN_MIN - 1e-12:
        send(ser_pan, f"T{val:.4f}")
        time.sleep(INTERVAL_SEC)
        val -= PAN_STEP_RAD

def tilt_cycle():
    """
    tilt 값을 MAX→0 (내림), 0→MAX (올림) 무한 반복 생성
    """
    while True:
        # 내려가기
        tilt = TILT_MAX
        while tilt >= 0 - 1e-12:
            yield tilt
            tilt -= TILT_STEP_RAD
        # 올라가기
        tilt = 0 + TILT_STEP_RAD
        while tilt <= TILT_MAX + 1e-12:
            yield tilt
            tilt += TILT_STEP_RAD

def main():
    pan = serial.Serial(PORT_PAN, BAUD, timeout=1)
    tilt = serial.Serial(PORT_TILT, BAUD, timeout=1)

    try:
        # 초기화
        send(pan, "R")
        send(tilt, "R")
        time.sleep(1.0)
        send(pan, "S")
        send(tilt, "S")
        time.sleep(1.0)

        gen = tilt_cycle()

        # 첫 tilt 세팅 후 pan 왕복
        current_tilt = next(gen)
        send(tilt, f"T{current_tilt:.4f}")
        time.sleep(INTERVAL_SEC)
        sweep_pan_once(pan)

        # 반복
        for current_tilt in gen:
            send(tilt, f"T{current_tilt:.4f}")
            time.sleep(INTERVAL_SEC)
            sweep_pan_once(pan)

    except KeyboardInterrupt:
        pass
    finally:
        try:
            send(pan, "R")
            pan.close()
        except Exception:
            pass
        try:
            send(tilt, "R")
            tilt.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
