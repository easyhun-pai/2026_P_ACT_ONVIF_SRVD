#!/usr/bin/env python3
"""
팬/틸트 이동 한 줄 명령 — 장비에서 실행, ONVIF(127.0.0.1:1000)로 보낸다 (onvif_srvd 를 멈출 필요 없음)

  python3 onvif_move.py 0 90                # 팬 0°, 틸트 90° (기본 단위 = 도. 틸트 0° = 위, 90° = 수평 정면)
  python3 onvif_move.py 0 1.571 --rad       # 라디안으로
  python3 onvif_move.py 30 70 --speed 0.5   # 속도 0.1~1.0 (1.0 = 팬 3.0 rad/s). 없으면 ONVIF 기본 속도
  python3 onvif_move.py --preset 1          # 프리셋 1 로
  python3 onvif_move.py --list              # 프리셋 목록
  python3 onvif_move.py                     # 지금 각도만 표시 (+ ONVIF GetStatus: 실측, MoveStatus, Error)
  기본은 도착할 때까지 기다리며 각도를 보여 준다. --no-wait 로 보내기만.
"""
import argparse
import math
import re
import sys
import time
import urllib.request

ONVIF_URL = "http://127.0.0.1:1000/onvif/ptz_service"
PROFILE = "MainStream"
LIVE_PATH = "/run/onvif_srvd/live"
PRESET_PATH = "/var/lib/onvif_srvd/presets.txt"
ARRIVE_TOL = 0.03
HELP = """Move pan/tilt through ONVIF (run on the device; no need to stop onvif_srvd).
  onvif_move.py PAN TILT [--rad] [--speed 0.1-1.0] [--no-wait]   (PAN/TILT in degrees by default)
  onvif_move.py --preset TOKEN | --list | (no args: show current angles)
Tilt: 0 deg = up (dome top), 90 deg = horizontal front."""


def soap(body, timeout=3):
    env = ('<?xml version="1.0" encoding="utf-8"?>'
           '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
           ' xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
           f'<s:Body>{body}</s:Body></s:Envelope>')
    req = urllib.request.Request(ONVIF_URL, data=env.encode(),
                                 headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def read_live():
    try:
        txt = open(LIVE_PATH, encoding="utf-8").read()
    except OSError:
        return None
    d = {}
    for l in txt.splitlines():
        m = re.match(r"^(pan|tilt)\s+current\s+([-\d.]+) rad.*?target\s+([-\d.]+) rad.*offset\s+[-\d.]+\s+(.*)$", l)
        if m:
            d[m.group(1)] = (float(m.group(2)), float(m.group(3)), m.group(4).strip())
    return d if "pan" in d and "tilt" in d else None


def onvif_status():
    """GetStatus: (pan, tilt, MoveStatus, Error). mk3-basic stream 빌드부터 pan/tilt 는 실측, Error 는 감시 결과."""
    try:
        r = soap(f'<tptz:GetStatus><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken></tptz:GetStatus>')
    except Exception as e:
        return None, str(e)
    pt = re.search(r'Position>.*?PanTilt[^>]*x="([-\d.eE]+)"[^>]*y="([-\d.eE]+)"', r, re.S)
    mv = re.search(r'MoveStatus>.*?PanTilt>(\w+)<', r, re.S)
    er = re.search(r'Error>([^<]*)<', r)
    if not pt:
        return None, "no Position in GetStatus"
    return (float(pt[1]), float(pt[2]), mv[1] if mv else "?", er[1] if er else ""), ""


def show_onvif(prefix=""):
    st, err = onvif_status()
    if not st:
        print(prefix + f"(GetStatus failed: {err})")
        return
    print(f"{prefix}pan {math.degrees(st[0]):+6.1f} deg  tilt {math.degrees(st[1]):5.1f} deg  "
          f"MoveStatus {st[2]}" + (f"  Error {st[3]}" if st[3] else "  Error -"))


def show(prefix=""):
    lv = read_live()
    if not lv:
        print(prefix + "(no live data - onvif_srvd not running or motors not armed)")
        return None
    p, t = lv["pan"], lv["tilt"]
    print(f"{prefix}pan {math.degrees(p[0]):+6.1f} deg ({p[0]:+.3f} rad) [{p[2]}]   "
          f"tilt {math.degrees(t[0]):5.1f} deg ({t[0]:.3f} rad) [{t[2]}]")
    return lv


def presets():
    out = []
    try:
        for l in open(PRESET_PATH, encoding="utf-8"):
            f = l.split()
            if len(f) >= 3:
                out.append((f[0], float(f[1]), float(f[2]), " ".join(f[4:]) if len(f) > 4 else ""))
    except OSError:
        pass
    return out


def wait_arrive(pan, tilt, timeout=20.0):
    t0, first = time.time(), None
    while time.time() - t0 < timeout:
        time.sleep(0.25)
        lv = read_live()
        if not lv:
            continue
        ok = abs(math.remainder(lv["pan"][0] - pan, 2 * math.pi)) < ARRIVE_TOL and abs(lv["tilt"][0] - tilt) < ARRIVE_TOL
        if ok:
            first = first or time.time()
            if time.time() - first >= 0.45:
                return True, time.time() - t0
        else:
            first = None
    return False, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pan", nargs="?", type=float)
    ap.add_argument("tilt", nargs="?", type=float)
    ap.add_argument("--rad", action="store_true", help="PAN/TILT in radians (default: degrees)")
    ap.add_argument("--speed", type=float, help="0.1-1.0 (1.0 = pan 3.0 rad/s). default: ONVIF default speed")
    ap.add_argument("--preset", help="go to preset token (see --list)")
    ap.add_argument("--list", action="store_true", help="list presets")
    ap.add_argument("--no-wait", action="store_true", help="send and exit")
    a = ap.parse_args()

    if a.list:
        for tok, p, t, name in presets():
            print(f"  {tok:>4}  pan {math.degrees(p):+6.1f} deg  tilt {math.degrees(t):5.1f} deg  {name}")
        return 0
    if a.preset is not None:
        target = next(((p, t) for tok, p, t, _ in presets() if tok == a.preset), None)
        if target is None:
            print(f"[ERROR] preset '{a.preset}' not found (--list)")
            return 2
        show("before: ")
        soap(f'<tptz:GotoPreset><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken>'
             f'<tptz:PresetToken>{a.preset}</tptz:PresetToken></tptz:GotoPreset>')
        print(f"GotoPreset {a.preset} -> pan {math.degrees(target[0]):+.1f} deg tilt {math.degrees(target[1]):.1f} deg")
    elif a.pan is not None and a.tilt is not None:
        pan, tilt = (a.pan, a.tilt) if a.rad else (math.radians(a.pan), math.radians(a.tilt))
        target = (pan, tilt)
        spd = ""
        if a.speed:
            s = max(0.1, min(1.0, a.speed))
            spd = f'<tptz:Speed><tt:PanTilt x="{s:.2f}" y="{s:.2f}"/></tptz:Speed>'
        show("before: ")
        soap(f'<tptz:AbsoluteMove><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken>'
             f'<tptz:Position><tt:PanTilt x="{pan:.4f}" y="{tilt:.4f}"/></tptz:Position>{spd}</tptz:AbsoluteMove>')
        print(f"AbsoluteMove -> pan {math.degrees(pan):+.1f} deg tilt {math.degrees(tilt):.1f} deg" + (f" speed {a.speed}" if a.speed else ""))
    elif a.pan is None:
        show()
        show_onvif("onvif:  ")
        return 0
    else:
        print("[ERROR] give both PAN and TILT")
        return 2

    if a.no_wait:
        return 0
    ok, dt = wait_arrive(*target)
    show("after:  ")
    time.sleep(0.6)   # onvif 감시 판정(0.5초 주기)이 도착을 반영할 시간
    show_onvif("onvif:  ")
    print(f"{'arrived' if ok else 'NOT arrived (timeout / limit / motor off?)'} in {dt:.1f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
