#!/usr/bin/env python3
"""프리셋 이름 띄어쓰기 시험 (장비 안에서, sudo). presets.txt 를 백업하고 끝나면 되돌린다.
  sudo python3 preset_name_test.py
"""
import json
import re
import shutil
import subprocess
import time
import urllib.request

URL = "http://127.0.0.1:1000/onvif/ptz_service"
P = "/var/lib/onvif_srvd/presets.txt"
BK = "/root/preset_name_test_backup.txt"
fails = 0


def soap(body):
    env = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
           ' xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
           f'<s:Body>{body}</s:Body></s:Envelope>')
    r = urllib.request.urlopen(urllib.request.Request(URL, data=env.encode("utf-8"),
                               headers={"Content-Type": "application/soap+xml; charset=utf-8"}), timeout=8)
    return r.read().decode("utf-8")


def set_preset(token, name):
    t = f"<tptz:PresetToken>{token}</tptz:PresetToken>" if token else ""
    x = soap(f"<tptz:SetPreset><tptz:ProfileToken>JetsonPTZ</tptz:ProfileToken>{t}"
             f"<tptz:PresetName>{name}</tptz:PresetName></tptz:SetPreset>")
    m = re.search(r"PresetToken>([^<]*)<", x)
    return m.group(1) if m else None


def get_presets():
    x = soap("<tptz:GetPresets><tptz:ProfileToken>JetsonPTZ</tptz:ProfileToken></tptz:GetPresets>")
    out = {}
    for m in re.finditer(r'<\w+:Preset token="([^"]*)">(.*?)</\w+:Preset>', x, re.S):
        name = re.search(r"Name>([^<]*)<", m.group(2))
        pt = re.search(r'PanTilt x="([^"]*)" y="([^"]*)"', m.group(2))
        out[m.group(1)] = (name.group(1) if name else "", round(float(pt.group(1)), 3), round(float(pt.group(2)), 3))
    return out


def unesc(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:<52} 기대 {want!r}  결과 {got!r}")


shutil.copy2(P, BK)
try:
    before = get_presets()
    print("시작 프리셋:", before)

    print("\n== 1. 띄어쓰기 이름 저장")
    check("SetPreset 51 'Front door'", set_preset("51", "Front door"), "51")
    check("SetPreset 52 '정문 입구 2층'", set_preset("52", "정문 입구 2층"), "52")
    check("SetPreset 53 이름 줄바꿈·탭 → 공백", set_preset("53", "line1&#10;line2&#9;x"), "53")
    check("SetPreset 54 특수문자 'A&amp;B <x>'", set_preset("54", "A&amp;B &lt;x&gt;"), "54")
    check("SetPreset token 띄어쓰기 '5 5' → '5_5'", set_preset("5 5", "tok space"), "5_5")
    check("SetPreset 55 이름 앞뒤 공백 → 잘라냄", set_preset("55", "  Back gate  "), "55")

    g = get_presets()
    names = {k: unesc(v[0]) for k, v in g.items()}
    check("GetPresets 51 이름", names.get("51"), "Front door")
    check("GetPresets 52 이름", names.get("52"), "정문 입구 2층")
    check("GetPresets 53 이름", names.get("53"), "line1 line2 x")
    check("GetPresets 54 이름", names.get("54"), "A&B <x>")
    check("GetPresets 5_5 이름", names.get("5_5"), "tok space")
    check("GetPresets 55 이름", names.get("55"), "Back gate")
    for k, v in before.items():
        check(f"원래 프리셋 {k} 그대로 (이름·위치)", g.get(k), v)
    check("파일 줄 수 = 프리셋 수", len(open(P, encoding="utf-8").read().splitlines()), len(g))

    print("\n== 2. 서비스 재시작 뒤 (파일에서 다시 읽기)")
    subprocess.run(["systemctl", "restart", "onvif_srvd"], check=True)
    time.sleep(4)
    check("재시작 뒤 GetPresets 같음", get_presets(), g)

    print("\n== 3. edge ptz_api 가 읽는 이름 (127.0.0.1:7777/ptz/presets)")
    try:
        j = json.loads(urllib.request.urlopen("http://127.0.0.1:7777/ptz/presets", timeout=5).read())["presets"]
        check("ptz_api 51 이름", j.get("51", {}).get("name"), "Front door")
        check("ptz_api 52 이름", j.get("52", {}).get("name"), "정문 입구 2층")
    except Exception as e:
        check("ptz_api 응답", str(e), "ok")

    print("\n== 4. 깨진 줄이 있는 파일 → 그 줄만 버림")
    with open(P, "a", encoding="utf-8") as f:
        f.write("garbage line here\n7 notanumber 1 2 x\n\n")
    g2 = get_presets()
    check("깨진 줄 무시, 나머지 그대로", g2, g)

    print("\n== 5. 옛 방식으로 망가진 파일 흉내 (이름 띄어쓰기 + 뒤 프리셋)")
    with open(P, "w", encoding="utf-8") as f:
        f.write("1 2.078 1.466 0.83 Preset1\n2 0.672 1.5708 0 Front door\n3 0.5 0.3 0.2 Gate\n4 -1 0.1 0.4 Yard\n")
    g3 = {k: (unesc(v[0]), v[1], v[2]) for k, v in get_presets().items()}
    check("4개 모두 제자리", g3, {"1": ("Preset1", 2.078, 1.466), "2": ("Front door", 0.672, 1.571),
                               "3": ("Gate", 0.5, 0.3), "4": ("Yard", -1.0, 0.1)})

    print("\n== 6. RemovePreset 뒤 나머지 유지")
    soap("<tptz:RemovePreset><tptz:ProfileToken>JetsonPTZ</tptz:ProfileToken>"
         "<tptz:PresetToken>2</tptz:PresetToken></tptz:RemovePreset>")
    g4 = {k: unesc(v[0]) for k, v in get_presets().items()}
    check("2 만 지워짐", g4, {"1": "Preset1", "3": "Gate", "4": "Yard"})
    check("임시 파일 안 남음", subprocess.run(["ls", P + ".tmp"], capture_output=True).returncode != 0, True)
finally:
    shutil.copy2(BK, P)
    print("\npresets.txt 되돌림:", subprocess.run(["md5sum", P, BK], capture_output=True, text=True).stdout.replace("\n", " "))

print(f"\n== {'ALL PASS' if not fails else f'{fails} FAIL'}")
