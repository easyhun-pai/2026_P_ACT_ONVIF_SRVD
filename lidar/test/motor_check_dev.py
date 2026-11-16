#!/usr/bin/env python3
"""장비 안에서 sudo 로 (onvif_srvd 를 멈춘 뒤): 모터 FW v2.5.3 제작사 확인 항목 시험.

  sudo python3 motor_check_dev.py '<expected json>'

제작사 메일(2026-11-13 조성윤 대표)과 매뉴얼(Kestrel_Motor_Controller_FW_v2.5.3_manual.md) 기준:
  - 설정 조회: V, I(범위·offset·Guard), E(튜닝: velocity P), Q(플래그·온도·발열)
  - 팬 끝단 발열: S -> T-3 / T3 (설정 범위 끝까지, 5초 대기) -> Q 로 heat (3 W 이하 정상)
  - 팬 유지 떨림: T-1.5 / T0 / T1.5 에서 A500 -> peak-to-peak (0.15~0.6 도 정상)
  - 틸트: 위 끝(T1.57), 1.45, 아래 끝(T0) 유지 발열, 중간(0.8) 떨림. 0 아래로는 보내지 않는다
  - 끝나면 원래 목표 각도로 되돌림
  - 설정 바꾸는 명령(R, CALIBRATE, M*, O, X, EW, ED, CZ, CF)은 보내지 않는다
출력: 마지막 줄 RESULT <json>
"""
import json
import os
import re
import select
import struct
import sys
import termios
import time

EXP = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
PORTS = (("pan", "/dev/ttyAMA0"), ("tilt", "/dev/ttyAMA2"))
FORBIDDEN = re.compile(r"^(R|CALIBRATE|M|O|X|EW|ED|CZ|CF|CX|EA|ET|F)", re.I)


def open_port(p):
    fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL; a[3] = 0
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


def read_for(fd, sec, until=None):
    buf, end = b"", time.time() + sec
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                buf += os.read(fd, 4096)
            except BlockingIOError:
                pass
            if until and re.search(until, buf):
                time.sleep(0.05)
                try:
                    buf += os.read(fd, 4096)
                except BlockingIOError:
                    pass
                break
    return buf.decode("utf-8", "replace")


def cmd(fd, c, wait=0.6, until=None, log=None):
    assert not FORBIDDEN.match(c) or c == "S", f"forbidden command {c}"
    termios.tcflush(fd, termios.TCIFLUSH)
    os.write(fd, (c + "\n").encode())
    out = read_for(fd, wait, until)
    if log is not None:
        log.append(f">>> {c}\n{out.strip()}")
    return out


def q(fd):
    for _ in range(3):
        out = cmd(fd, "Q", 0.4, rb"Q[0-9A-Fa-f]{64}")
        m = re.search(r"Q([0-9A-Fa-f]{64})", out)
        if m:
            f = struct.unpack("<BBHhhhhHhHhhHHIH", bytes.fromhex(m[1]))
            return dict(flags=f[2], tgt=f[3] / 1000, cur=f[4] / 1000, vq=f[6] / 1000, vlim=f[7] / 1000,
                        temp=f[8] / 100, heat=f[9] / 100, room=f[10] / 100, trip=f[11] / 100, trips=f[12], foc=f[13])
    return None


def num(pat, s, default=None):
    m = re.search(pat, s, re.I)
    return float(m[1]) if m else default


def hold_heat(fd, target, log, settle=5.0):
    cmd(fd, f"T{target}", 0.3, log=log)
    time.sleep(settle)
    xs = []
    for _ in range(4):
        r = q(fd)
        if r:
            xs.append(r)
        time.sleep(0.25)
    if not xs:
        return None
    return dict(target=target, cur=xs[-1]["cur"], heat=round(max(x["heat"] for x in xs), 2),
                vq=round(max(abs(x["vq"]) for x in xs), 2), temp=xs[-1]["temp"])


def wobble(fd, target, log, settle=3.0):
    cmd(fd, f"T{target}", 0.3, log=log)
    time.sleep(settle)
    out = cmd(fd, "A500", 2.5, rb"(?i)std[^\n]*\n", log=log)
    pp = num(r"(?:peak[- ]to[- ]peak|p-?p)\D{0,12}?([-\d.]+(?:e-?\d+)?)", out)
    std = num(r"std\D{0,12}?([-\d.]+(?:e-?\d+)?)", out)
    return dict(target=target, pp_deg=round(pp * 57.2958, 3) if pp is not None else None,
                std_deg=round(std * 57.2958, 3) if std is not None else None)


res = {}
for name, port in PORTS:
    log, r = [], {}
    fd = open_port(port)
    try:
        r["V"] = (re.search(r"v\d+\.\d+\.\d+[\w-]*", cmd(fd, "V", 0.5, rb"v\d+\.\d+\.\d+", log)) or [None])[0]
        info = cmd(fd, "I", 1.5, None, log)
        tune = cmd(fd, "E", 1.5, None, log)
        r["min"] = num(r"Min Angle\D*?(-?[\d.]+)", info)
        r["max"] = num(r"Max Angle\D*?(-?[\d.]+)", info)
        r["offset"] = num(r"Sensor Offset\D*?(-?[\d.]+)", info)
        r["guard"] = (re.search(r"Guard:[^\r\n]*", info) or [""])[0]
        r["model"] = (re.search(r"Guard:\s*(\S+)", info) or [None, None])[1]
        # velocity P: E 의 live 줄 우선, 없으면 I
        vp = re.findall(r"live\s*:\s*velocity P/I/D\s*([\d.]+)", tune) or re.findall(r"velocity P/I/D\s*([\d.]+)", info)
        r["vel_p_all"] = vp
        r["vel_p"] = float(vp[-1]) if vp else None
        st = q(fd)
        r["q0"] = st
        orig = st["tgt"] if st else None
        if st and not (st["flags"] & 1):
            cmd(fd, "S", 1.5, None, log)
            time.sleep(1)
            r["started"] = True
        holds, wob = [], []
        if name == "pan":
            for t in (-3, 3):   # 설정 범위 끝까지 (펌웨어가 끝 값으로 자름)
                holds.append(hold_heat(fd, t, log))
            for t in (-1.5, 0, 1.5):
                wob.append(wobble(fd, t, log))
        else:
            for t in (1.57, 1.45, 0):   # 0 아래로 보내지 않음
                holds.append(hold_heat(fd, t, log))
            wob.append(wobble(fd, 0.8, log))
        r["holds"], r["wobble"] = holds, wob
        if orig is not None:
            cmd(fd, f"T{max(orig, 0) if name == 'tilt' else orig:.3f}", 0.3, log=log)
            time.sleep(3)
        r["q1"] = q(fd)
        r["back"] = r["q1"]["cur"] if r["q1"] else None
        r["orig"] = orig
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {e}"
        try:
            if r.get("orig") is None and r.get("q0"):
                cmd(fd, f"T{r['q0']['tgt']:.3f}", 0.3)
        except Exception:
            pass
    finally:
        os.close(fd)
    r["log"] = "\n".join(log)
    res[name] = r
print("RESULT " + json.dumps(res, ensure_ascii=False))
