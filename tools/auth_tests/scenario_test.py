#!/usr/bin/env python3
"""장비 파일 상태별 ONVIF 계정 확인 시험 (PC 에서, ptz018 에 ssh 로 파일을 바꿔 가며). 끝나면 원래 파일로 되돌린다.

  python scenario_test.py <장비IP> <ssh 비밀번호> <웹 비밀번호>
"""
import base64
import datetime
import hashlib
import os
import sys
import urllib.error
import urllib.request

import paramiko

HOST, SSHPW, WEBPW = sys.argv[1], sys.argv[2], sys.argv[3]
URL = f"http://{HOST}:1000/onvif/device_service"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PT = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#"
DEVINFO = '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>'

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="ptz", password=SSHPW, timeout=8)


def sh(cmd, sudo=True):
    b = base64.b64encode(cmd.encode()).decode()
    full = f"echo {SSHPW} | sudo -S -p '' sh -c \"$(echo {b} | base64 -d)\"" if sudo else cmd
    _, o, e = c.exec_command(full, timeout=30)
    return o.read().decode() + e.read().decode()


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tok(pw, digest=True, user="admin"):
    n = os.urandom(16)
    cr = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if digest:
        v = base64.b64encode(hashlib.sha1(n + cr.encode() + pw.encode()).digest()).decode()
        t = "PasswordDigest"
    else:
        v, t = esc(pw), "PasswordText"
    return (f'<wsse:Security s:mustUnderstand="1" xmlns:wsse="{WSSE}" xmlns:wsu="{WSU}"><wsse:UsernameToken>'
            f'<wsse:Username>{user}</wsse:Username><wsse:Password Type="{PT}{t}">{v}</wsse:Password>'
            f'<wsse:Nonce>{base64.b64encode(n).decode()}</wsse:Nonce><wsu:Created>{cr}</wsu:Created>'
            f'</wsse:UsernameToken></wsse:Security>')


def send(header="", url=URL):
    env = (f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
           f'{"<s:Header>" + header + "</s:Header>" if header else ""}<s:Body>{DEVINFO}</s:Body></s:Envelope>')
    req = urllib.request.Request(url, data=env.encode("utf-8"), headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    try:
        r = urllib.request.urlopen(req, timeout=6)
        return "ok" if r.status == 200 else str(r.status)
    except urllib.error.HTTPError as e:
        return "deny" if "NotAuthorized" in e.read().decode(errors="replace") else str(e.code)


fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:<58} 기대 {want:<4} 결과 {got}")


AUTH, EDGE, DEV, OFF = "/var/lib/onvif_srvd/onvif_auth", "/home/ptz/edge/.device_auth", "/var/lib/onvif_srvd/device_id", "/var/lib/onvif_srvd/onvif_auth_off"
BK = "/root/onvif_auth_test_backup"
dev = sh(f"cat {DEV}").strip()
serial = dev.split("-")[-1]
print(f"장비 {dev}\n")
sh(f"mkdir -p {BK} && cp -p {EDGE} {BK}/device_auth && cp -p {AUTH} {BK}/onvif_auth 2>/dev/null; cp -p {DEV} {BK}/device_id")


def put_auth(text):
    b = base64.b64encode(text.encode()).decode()
    sh(f"umask 077; echo {b} | base64 -d > {AUTH}")


def set_edge_hash(pw):
    h = "null" if pw is None else '"' + hashlib.sha256(f"{dev}:{pw}".encode()).hexdigest() + '"'
    sh(f"cat > {EDGE} <<'E'\n{{\"custom_password_hash\": {h}, \"session\": \"test\"}}\nE\nchown ptz:ptz {EDGE}; chmod 600 {EDGE}")


try:
    print("== A. 원문 파일에 옛 비밀번호 (해시와 안 맞음)")
    put_auth("oldpassword1")
    check("Digest 맞는 비밀번호 → 원문 없음으로 거부", send(tok(WEBPW)), "deny")
    check("Text 맞는 비밀번호 → 해시로 통과", send(tok(WEBPW, False)), "ok")
    check("Digest 옛 비밀번호 → 거부", send(tok("oldpassword1")), "deny")

    print("\n== B. 원문 파일 끝에 줄바꿈")
    put_auth(WEBPW + "\n")
    check("Digest 맞는 비밀번호", send(tok(WEBPW)), "ok")

    print("\n== C. 원문 파일 없음 + 웹 비밀번호 안 정함 (시리얼)")
    sh(f"rm -f {AUTH}")
    set_edge_hash(None)
    check("Digest 시리얼", send(tok(serial)), "ok")
    check("Text 시리얼", send(tok(serial, False)), "ok")
    check("Digest 예전 웹 비밀번호 → 거부", send(tok(WEBPW)), "deny")

    print("\n== D. .device_auth 파일 자체가 없음 (edge 처음 설치) → 시리얼")
    sh(f"rm -f {EDGE}")
    check("Digest 시리얼", send(tok(serial)), "ok")

    print("\n== E. 특수문자·한글 비밀번호 (& < > \" ' 공백 한글)")
    sp = 'p&<>"\' 한글#1'
    set_edge_hash(sp)
    put_auth(sp)
    check("Digest 특수문자 비밀번호", send(tok(sp)), "ok")
    check("Text 특수문자 비밀번호 (XML 이스케이프)", send(tok(sp, False)), "ok")
    check("Digest 시리얼 → 거부 (비밀번호 정한 뒤)", send(tok(serial)), "deny")

    print("\n== F. 장비 ID 파일 없음 → 밖은 모두 거부, 장비 안은 허용")
    sh(f"rm -f {DEV}")
    check("Digest 맞는 비밀번호 → 거부 (기준 없음)", send(tok(sp)), "deny")
    loc = sh("cd /home/ptz/workspace/onvif_setup && python3 onvif_move.py | tail -1", sudo=False)
    check("장비 안 127.0.0.1 계정 없이 (onvif_move.py GetStatus)", "ok" if "MoveStatus" in loc else loc.strip()[:40], "ok")
    sh(f"cp -p {BK}/device_id {DEV}")

    print("\n== G. 비상 해제 파일 (onvif_auth_off)")
    sh(f"touch {OFF}")
    check("헤더 없음 → 허용", send(), "ok")
    check("틀린 비밀번호 → 허용", send(tok("wrong")), "ok")
    sh(f"rm -f {OFF}")
    check("해제 파일 지운 뒤 헤더 없음 → 거부", send(), "deny")
finally:
    sh(f"cp -p {BK}/device_auth {EDGE}; cp -p {BK}/device_id {DEV}; "
       f"if [ -f {BK}/onvif_auth ]; then cp -p {BK}/onvif_auth {AUTH}; else rm -f {AUTH}; fi; rm -f {OFF}")
    print("\n원래 파일로 되돌림:", sh(f"md5sum {EDGE} {BK}/device_auth {DEV} {BK}/device_id | cut -c1-8 | tr '\\n' ' '"))
    check("되돌린 뒤 Digest 웹 비밀번호", send(tok(WEBPW)), "ok")

print(f"\n== {'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)
