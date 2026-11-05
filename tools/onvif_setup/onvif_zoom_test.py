#!/usr/bin/env python3
"""onvif_srvd 줌 위치 시험 (장비에서 실행, 요청서 시험 1~4 + 홈 저장 + 응답 속도)

  python3 onvif_zoom_test.py
줌은 edge API(7777)로 줌카메라를 직접 움직이고(웹 화면과 같은 경로),
프리셋·상태·상대이동은 onvif_srvd(1000)에 ONVIF 로 직접 보낸다(NVR 과 같은 경로).
시험 프리셋(token ztest)은 끝에 지우고, 줌은 시작 값으로 되돌린다.
"""
import re
import sys
import time
import urllib.request

ONVIF = "http://127.0.0.1:1000/onvif/ptz_service"
EDGE = "http://127.0.0.1:7777"
PROFILE = "MainStream"
TOKEN = "ztest"
results = []


def soap(inner):
    env = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
           ' xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
           f'<s:Body>{inner}</s:Body></s:Envelope>')
    req = urllib.request.Request(ONVIF, data=env.encode(), headers={"Content-Type": "application/soap+xml"})
    return urllib.request.urlopen(req, timeout=5).read().decode()


def edge(path, method="GET"):
    req = urllib.request.Request(EDGE + path, method=method, data=b"" if method == "POST" else None)
    return urllib.request.urlopen(req, timeout=8).read().decode()


def onvif_zoom():
    t0 = time.time()
    r = soap(f'<tptz:GetStatus><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken></tptz:GetStatus>')
    ms = (time.time() - t0) * 1000
    m = re.search(r'Position>.*?Zoom[^>]*\bx="([-\d.eE]+)"', r, re.S)
    return float(m.group(1)), ms


def cam_zoom():
    return float(re.search(r'"zoom":\s*([-\d.]+)', edge("/zoom/current")).group(1))


def preset_zoom():
    for l in open("/var/lib/onvif_srvd/presets.txt"):
        f = l.split()
        if f and f[0] == TOKEN:
            return float(f[3])
    return None


def check(name, got, want, tol=0.02):
    ok = got is not None and abs(got - want) <= tol
    results.append(ok)
    print(f"{'OK ' if ok else 'NG '} {name}: got {got}, want {want:.3f} (+-{tol})")


def settle(sec=3.0):
    time.sleep(sec)


start = cam_zoom()
print(f"start: camera zoom {start:.3f}, onvif zoom {onvif_zoom()[0]:.3f}")
try:
    # 1) 웹 경로로 줌 3배 -> ONVIF GetStatus 가 실제 값
    edge("/zoom/ratio/3"); settle()
    real = cam_zoom()
    check("1 GetStatus after web zoom x3", onvif_zoom()[0], real)
    check("1 camera at x3 (2/9)", real, 2 / 9, 0.03)

    # 2) ONVIF SetPreset 직접 -> presets.txt 에 실제 줌
    soap(f'<tptz:SetPreset><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken><tptz:PresetName>{TOKEN}</tptz:PresetName>'
         f'<tptz:PresetToken>{TOKEN}</tptz:PresetToken></tptz:SetPreset>')
    check("2 presets.txt zoom", preset_zoom(), real)

    # 3) 웹으로 1배 -> ONVIF GotoPreset -> 줌카메라가 프리셋 줌으로
    edge("/zoom/ratio/1"); settle()
    check("3 GetStatus after web zoom x1", onvif_zoom()[0], 0.0)
    soap(f'<tptz:GotoPreset><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken>'
         f'<tptz:PresetToken>{TOKEN}</tptz:PresetToken></tptz:GotoPreset>'); settle()
    check("3 camera zoom after GotoPreset", cam_zoom(), real)

    # 4) 연속 줌(웹 경로) 뒤 ONVIF RelativeMove 줌 +0.1 (=+0.05 위치, REL_SCALE_ZOOM 0.5) -> 실제 값 기준
    edge("/zoom/continuous/0.5", "POST"); time.sleep(0.8); edge("/zoom/stop", "POST"); settle()
    base = cam_zoom()
    check("4 GetStatus after continuous zoom", onvif_zoom()[0], base)
    soap(f'<tptz:RelativeMove><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken>'
         f'<tptz:Translation><tt:Zoom x="0.1"/></tptz:Translation></tptz:RelativeMove>'); settle()
    check("4 RelativeMove +0.1 from real base", cam_zoom(), min(1.0, base + 0.05))

    # 5) SetHomePosition -> home.txt 에 실제 줌
    soap(f'<tptz:SetHomePosition><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken></tptz:SetHomePosition>')
    hz = float(open("/var/lib/onvif_srvd/home.txt").read().split()[2])
    check("5 home.txt zoom", hz, cam_zoom())

    # 6) GetStatus 응답 속도 (줌카메라를 기다리지 않아야 함)
    ms = sorted(onvif_zoom()[1] for _ in range(20))
    ok = ms[-1] < 100
    results.append(ok)
    print(f"{'OK ' if ok else 'NG '} 6 GetStatus latency: median {ms[10]:.1f} ms, max {ms[-1]:.1f} ms (<100)")
finally:
    soap(f'<tptz:RemovePreset><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken>'
         f'<tptz:PresetToken>{TOKEN}</tptz:PresetToken></tptz:RemovePreset>')
    edge(f"/zoom/absolute/{start:.3f}"); settle()
    print(f"cleanup: preset {TOKEN} removed={preset_zoom() is None}, zoom back to {cam_zoom():.3f}")

print(f"VERDICT: {'PASS' if all(results) else 'FAIL'} ({sum(results)}/{len(results)})")
sys.exit(0 if all(results) else 1)
