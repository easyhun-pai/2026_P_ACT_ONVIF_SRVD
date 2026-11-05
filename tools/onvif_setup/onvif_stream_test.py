#!/usr/bin/env python3
"""스트리밍 모드(이동 감시) 시험 (장비에서, onvif 켠 채로). 이동 중/후 GetStatus 를 찍어 MOVING/IDLE, 실측 위치, Error 를 확인.

  python3 onvif_stream_test.py move PAN TILT [SPEED]   AbsoluteMove 후 12초 동안 0.3초마다 GetStatus
  python3 onvif_stream_test.py cont VX VY SEC [stop|zero]   연속 이동 SEC 초 뒤 Stop(또는 속도 0) 후 8초 관찰
  python3 onvif_stream_test.py watch SEC               움직이지 않고 SEC 초 관찰
"""
import re
import sys
import time
import urllib.request

ONVIF = "http://127.0.0.1:1000/onvif/ptz_service"
P = "<tptz:ProfileToken>MainStream</tptz:ProfileToken>"


def soap(inner):
    env = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
           ' xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
           f'<s:Body>{inner}</s:Body></s:Envelope>')
    req = urllib.request.Request(ONVIF, data=env.encode(), headers={"Content-Type": "application/soap+xml"})
    return urllib.request.urlopen(req, timeout=5).read().decode()


def status():
    r = soap(f"<tptz:GetStatus>{P}</tptz:GetStatus>")
    pt = re.search(r'Position>.*?PanTilt[^>]*x="([-\d.eE]+)"[^>]*y="([-\d.eE]+)"', r, re.S)
    mv = re.search(r'MoveStatus>.*?PanTilt>(\w+)<', r, re.S)
    er = re.search(r'Error>([^<]*)<', r)
    return float(pt[1]), float(pt[2]), mv[1] if mv else "?", er[1] if er else ""


def observe(sec, t0):
    end = time.time() + sec
    last = None
    while time.time() < end:
        p, t, m, e = status()
        line = f"{time.time() - t0:5.1f}s  pan {p:7.3f}  tilt {t:7.3f}  {m:6s} {e}"
        key = (round(p, 2), round(t, 2), m, e)
        if key != last:
            print(line)
            last = key
        time.sleep(0.3)


cmd = sys.argv[1] if len(sys.argv) > 1 else "watch"
t0 = time.time()
if cmd == "move":
    pan, tilt = float(sys.argv[2]), float(sys.argv[3])
    sp = f'<tptz:Speed><tt:PanTilt x="{sys.argv[4]}" y="{sys.argv[4]}"/></tptz:Speed>' if len(sys.argv) > 4 else ""
    soap(f'<tptz:AbsoluteMove>{P}<tptz:Position><tt:PanTilt x="{pan}" y="{tilt}"/></tptz:Position>{sp}</tptz:AbsoluteMove>')
    observe(12, t0)
elif cmd == "cont":
    vx, vy, sec, how = float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5] if len(sys.argv) > 5 else "stop"
    end = time.time() + sec
    while time.time() < end:
        soap(f'<tptz:ContinuousMove>{P}<tptz:Velocity><tt:PanTilt x="{vx}" y="{vy}"/></tptz:Velocity></tptz:ContinuousMove>')
        print(f"{time.time() - t0:5.1f}s  (continuous) {status()}")
        time.sleep(0.5)
    if how == "zero":
        soap(f'<tptz:ContinuousMove>{P}<tptz:Velocity><tt:PanTilt x="0" y="0"/></tptz:Velocity></tptz:ContinuousMove>')
    else:
        soap(f"<tptz:Stop>{P}<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>false</tptz:Zoom></tptz:Stop>")
    print(f"{time.time() - t0:5.1f}s  -> {how}")
    observe(8, t0)
else:
    observe(float(sys.argv[2]) if len(sys.argv) > 2 else 10, t0)
