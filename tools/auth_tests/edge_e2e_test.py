#!/usr/bin/env python3
"""edge 웹 비밀번호 변경·초기화 → ONVIF 계정 확인 연동 시험 (PC 에서). 끝나면 원래 비밀번호로 되돌린다.

  python edge_e2e_test.py <장비IP> <ssh 비밀번호> <지금 웹 비밀번호>
"""
import base64
import datetime
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

import paramiko

HOST, SSHPW, ORIG = sys.argv[1], sys.argv[2], sys.argv[3]
TMP = "Tmp-Pass#2026&x"
ONVIF = f"http://{HOST}:1000/onvif/device_service"
WEB = f"http://{HOST}"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PT = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="ptz", password=SSHPW, timeout=8)


def sh(cmd):
    b = base64.b64encode(cmd.encode()).decode()
    _, o, e = c.exec_command(f"echo {SSHPW} | sudo -S -p '' sh -c \"$(echo {b} | base64 -d)\"", timeout=30)
    return (o.read() + e.read()).decode(errors="replace")


def api(path, body, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(WEB + path, data=json.dumps(body).encode(), headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=8)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def login(pw):
    s, j = api("/api/auth/login", {"password": pw})
    return j.get("token") if s == 200 else None


def onvif(pw):
    n = os.urandom(16)
    cr = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = base64.b64encode(hashlib.sha1(n + cr.encode() + pw.encode()).digest()).decode()
    env = (f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Header>'
           f'<wsse:Security s:mustUnderstand="1" xmlns:wsse="{WSSE}" xmlns:wsu="{WSU}"><wsse:UsernameToken>'
           f'<wsse:Username>admin</wsse:Username><wsse:Password Type="{PT}PasswordDigest">{d}</wsse:Password>'
           f'<wsse:Nonce>{base64.b64encode(n).decode()}</wsse:Nonce><wsu:Created>{cr}</wsu:Created>'
           f'</wsse:UsernameToken></wsse:Security></s:Header><s:Body>'
           f'<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>')
    req = urllib.request.Request(ONVIF, data=env.encode(), headers={"Content-Type": "application/soap+xml"})
    try:
        return "ok" if urllib.request.urlopen(req, timeout=6).status == 200 else "?"
    except urllib.error.HTTPError as e:
        return "deny" if "NotAuthorized" in e.read().decode(errors="replace") else str(e.code)


fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:<56} 기대 {want:<6} 결과 {got}")


def auth_file():
    r = sh("stat -c '%a %U' /var/lib/onvif_srvd/onvif_auth 2>/dev/null && md5sum /var/lib/onvif_srvd/onvif_auth | cut -c1-32")
    return r.split() if r.strip() else None


md5 = lambda s: hashlib.md5(s.encode()).hexdigest()   # noqa: E731
serial = sh("cat /var/lib/onvif_srvd/device_id").strip().split("-")[-1]
sh("rm -f /var/lib/onvif_srvd/onvif_auth")
cur = ORIG
try:
    print("== 1. 웹 비밀번호 변경 (원래 → 임시)")
    t = login(ORIG)
    check("웹 로그인", "ok" if t else "fail", "ok")
    s, j = api("/api/auth/change-password", {"current": ORIG, "new": TMP}, t)
    check("변경 API", str(s), "200")
    cur = TMP if s == 200 else ORIG
    f = auth_file()
    check("원문 파일 생성 (권한 600 root, 내용 = 새 비밀번호)",
          "ok" if f and f[0] == "600" and f[1] == "root" and f[2] == md5(TMP) else str(f), "ok")
    check("ONVIF Digest 새 비밀번호", onvif(TMP), "ok")
    check("ONVIF Digest 옛 비밀번호", onvif(ORIG), "deny")

    print("\n== 2. 되돌리기 (임시 → 원래)")
    t = login(TMP)
    s, j = api("/api/auth/change-password", {"current": TMP, "new": ORIG}, t)
    check("변경 API", str(s), "200")
    cur = ORIG if s == 200 else TMP
    f = auth_file()
    check("원문 파일 = 원래 비밀번호", "ok" if f and f[2] == md5(ORIG) else str(f), "ok")
    check("ONVIF Digest 원래 비밀번호", onvif(ORIG), "ok")

    print("\n== 3. 초기화 → 시리얼, 다시 원래 비밀번호로")
    t = login(ORIG)
    s, j = api("/api/auth/reset-password", {}, t)
    check("초기화 API", str(s), "200")
    cur = serial if s == 200 else ORIG
    check("원문 파일 삭제", "gone" if auth_file() is None else "exists", "gone")
    check("ONVIF Digest 시리얼", onvif(serial), "ok")
    check("ONVIF Digest 원래 비밀번호 → 거부", onvif(ORIG), "deny")
    t = login(serial)
    s, j = api("/api/auth/change-password", {"current": serial, "new": ORIG}, t)
    check("원래 비밀번호 다시 설정", str(s), "200")
    cur = ORIG if s == 200 else serial
    check("ONVIF Digest 원래 비밀번호", onvif(ORIG), "ok")
finally:
    if cur != ORIG:
        t = login(cur)
        s, j = api("/api/auth/change-password", {"current": cur, "new": ORIG}, t)
        print(f"!! 원래 비밀번호로 복구 시도: {s} {j}")
    print("\n최종: 웹 로그인", "ok" if login(ORIG) else "FAIL", "/ ONVIF", onvif(ORIG))

print(f"\n== {'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)
