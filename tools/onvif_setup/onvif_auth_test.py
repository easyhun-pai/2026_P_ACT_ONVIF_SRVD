#!/usr/bin/env python3
"""ONVIF 계정 확인 시험 (장비 밖 PC 에서). 조회만 — 모터는 움직이지 않는다.

  python3 onvif_auth_test.py <장비IP>[:1000] --password <웹 비밀번호> [--lockout]

  --password   영상 비밀번호 (웹에서 정한 것, 안 정했으면 시리얼)
  --lockout    잠금 시험도 (이 PC IP 가 약 60초 잠김. 마지막에 풀리는 것까지 확인)
  --expect-digest-fail   비밀번호 원문 파일이 없는 장비: Digest 는 거부, Text 는 통과가 정상

장비 안(127.0.0.1)에서 돌리면 계정 없이도 다 허용이라 이 시험은 PC 에서 한다.
"""
import argparse
import base64
import datetime
import hashlib
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("host")
ap.add_argument("--password", required=True)
ap.add_argument("--lockout", action="store_true")
ap.add_argument("--expect-digest-fail", action="store_true")
a = ap.parse_args()
HOST = a.host if ":" in a.host else a.host + ":1000"
URL = f"http://{HOST}/onvif/device_service"
PW = a.password
S12, S11 = "http://www.w3.org/2003/05/soap-envelope", "http://schemas.xmlsoap.org/soap/envelope/"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PT = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#"

B = {
    "GetDeviceInformation": '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>',
    "GetSystemDateAndTime": '<GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/>',
    "GetCapabilities": '<GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"><Category>All</Category></GetCapabilities>',
    "GetServices": '<GetServices xmlns="http://www.onvif.org/ver10/device/wsdl"><IncludeCapability>false</IncludeCapability></GetServices>',
    "GetProfiles": '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>',
    "GetStreamUri": ('<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl"><StreamSetup>'
                     '<Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>'
                     '<Transport xmlns="http://www.onvif.org/ver10/schema"><Protocol>RTSP</Protocol></Transport>'
                     '</StreamSetup><ProfileToken>{tok}</ProfileToken></GetStreamUri>'),
    "PTZ GetStatus": '<GetStatus xmlns="http://www.onvif.org/ver20/ptz/wsdl"><ProfileToken>{tok}</ProfileToken></GetStatus>',
    "GetPresets": '<GetPresets xmlns="http://www.onvif.org/ver20/ptz/wsdl"><ProfileToken>{tok}</ProfileToken></GetPresets>',
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def tok(user="admin", pw=None, digest=True, pfx="wsse", env="s", nonce=True, typ=None, raw_pw=None,
        created=None, mu=True):
    pw = PW if pw is None else pw
    n = os.urandom(16) if nonce else b""
    c = created or now()
    if raw_pw is not None:
        val = raw_pw
    elif digest:
        val = base64.b64encode(hashlib.sha1(n + c.encode() + pw.encode()).digest()).decode()
    else:
        val = pw.replace("&", "&amp;").replace("<", "&lt;")
    t = typ if typ is not None else (PT + ("PasswordDigest" if digest else "PasswordText"))
    ta = f' Type="{t}"' if t else ""
    nn = f'<{pfx}:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{base64.b64encode(n).decode()}</{pfx}:Nonce>' if nonce else ""
    m = f' {env}:mustUnderstand="1"' if mu else ""
    return (f'<{pfx}:Security{m} xmlns:{pfx}="{WSSE}" xmlns:wsu="{WSU}">'
            f'<{pfx}:UsernameToken wsu:Id="UsernameToken-1"><{pfx}:Username>{user}</{pfx}:Username>'
            f'<{pfx}:Password{ta}>{val}</{pfx}:Password>{nn}'
            f'<wsu:Created>{c}</wsu:Created></{pfx}:UsernameToken></{pfx}:Security>')


def send(body, header="", soap11=False, raw=None):
    ns, ct = (S11, "text/xml; charset=utf-8") if soap11 else (S12, "application/soap+xml; charset=utf-8")
    env = raw if raw is not None else (
        f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="{ns}">'
        f'{"<s:Header>" + header + "</s:Header>" if header else ""}<s:Body>{body}</s:Body></s:Envelope>')
    req = urllib.request.Request(URL, data=env.encode(), headers={"Content-Type": ct})
    try:
        r = urllib.request.urlopen(req, timeout=6)
        return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


fails = 0
rows = []


def check(name, code, txt, want):
    """want: 'ok' = 200, 'deny' = NotAuthorized fault, 'mu' = MustUnderstand fault"""
    global fails
    na = "NotAuthorized" in txt
    if want == "ok":
        ok = code == 200 and "Fault" not in txt
    elif want == "deny":
        ok = code in (400, 401, 500) and na
    else:
        ok = code in (400, 500) and "MustUnderstand" in txt
    leak = PW in txt and len(PW) >= 4
    ok = ok and not leak
    fails += not ok
    got = "200" if code == 200 and "Fault" not in txt else f"{code}{' NotAuthorized' if na else ''}{' MustUnderstand' if 'MustUnderstand' in txt else ''}"
    print(f"{'PASS' if ok else 'FAIL'}  {name:<52} 기대 {want:<4} 결과 {got}{'  (응답에 비밀번호!)' if leak else ''}")


def alive():
    c, t = send(B["GetSystemDateAndTime"])
    return c == 200


# 프로필 토큰
c, r = send(B["GetProfiles"], tok(digest=False))
m = re.search(r'Profiles[^>]*token="([^"]+)"', r)
TOKEN = m[1] if m else "MainStream"
for k in B:
    B[k] = B[k].replace("{tok}", TOKEN)
print(f"대상 {URL}  프로필 {TOKEN}\n")

D = "deny" if a.expect_digest_fail else "ok"

print("== 1. 계정 없이")
for op in ("GetDeviceInformation", "GetProfiles", "GetStreamUri", "PTZ GetStatus", "GetPresets"):
    check(f"헤더 없음 {op}", *send(B[op]), "deny")
for op in ("GetSystemDateAndTime", "GetCapabilities", "GetServices"):
    check(f"헤더 없음 {op} (로그인 전 허용)", *send(B[op]), "ok")

print("\n== 2. 맞는 계정")
for op in ("GetDeviceInformation", "GetProfiles", "GetStreamUri", "PTZ GetStatus", "GetPresets"):
    check(f"Digest {op}", *send(B[op], tok()), D)
check("틀린 계정 GetSystemDateAndTime (로그인 전 허용)", *send(B["GetSystemDateAndTime"], tok(pw="nope")), "ok")
check("Text GetDeviceInformation", *send(B["GetDeviceInformation"], tok(digest=False)), "ok")
check("Digest 접두사 o (WCF)", *send(B["GetDeviceInformation"], tok(pfx="o")), D)
check("Digest SOAP 1.1", *send(B["GetDeviceInformation"], tok(env="s"), soap11=True), D)
check("Digest mustUnderstand 없음", *send(B["GetDeviceInformation"], tok(mu=False)), D)
check("Digest Nonce 없음", *send(B["GetDeviceInformation"], tok(nonce=False)), D)
check("Text Type 속성 없음", *send(B["GetDeviceInformation"], tok(digest=False, typ="")), "ok")
check("Text 비밀번호 숫자 문자참조(&#49; 등)",
      *send(B["GetDeviceInformation"], tok(raw_pw="".join(f"&#{ord(ch)};" for ch in PW), typ=PT + "PasswordText")), "ok")
check("Digest 아이디 앞뒤 공백", *send(B["GetDeviceInformation"], tok(user="  admin\n")), D)
check("Digest + wsa Action/To", *send(B["GetDeviceInformation"], tok() +
      '<a:Action s:mustUnderstand="1" xmlns:a="http://www.w3.org/2005/08/addressing">x</a:Action>'), D)
check("Digest Created 1년 전 (시각 검사 안 함)", *send(B["GetDeviceInformation"], tok(created="2025-11-05T00:00:00Z")), D)
hdr = tok()
check("같은 Digest 두 번째 (재사용)", *send(B["GetDeviceInformation"], hdr), D)

print("\n== 3. 틀린 계정 (4번까지만 — 5번째에 잠김)")
check("Digest 틀린 비밀번호", *send(B["GetDeviceInformation"], tok(pw=PW + "x")), "deny")
check("Text 틀린 비밀번호", *send(B["GetDeviceInformation"], tok(pw="wrong", digest=False)), "deny")
check("Digest 아이디 Admin (대문자)", *send(B["GetDeviceInformation"], tok(user="Admin")), "deny")
check("Digest 아이디 root", *send(B["PTZ GetStatus"], tok(user="root")), "deny")
check("맞는 계정 → 실패 기록 지워짐", *send(B["GetDeviceInformation"], tok(digest=False)), "ok")

print("\n== 4. 모양이 이상한 헤더 (실패로 세지 않거나 거부)")
check("Security 만, UsernameToken 없음", *send(B["GetDeviceInformation"],
      f'<wsse:Security s:mustUnderstand="1" xmlns:wsse="{WSSE}"/>'), "deny")
check("UsernameToken 이 Body 안에", *send(B["GetDeviceInformation"] + tok()), "deny")
check("Digest 값을 Text 로 표시", *send(B["GetDeviceInformation"], tok(typ=PT + "PasswordText")), "deny")
check("빈 비밀번호", *send(B["GetDeviceInformation"], tok(raw_pw="", typ=PT + "PasswordText")), "deny")
check("Text 비밀번호 앞뒤 공백 (그대로 비교)", *send(B["GetDeviceInformation"], tok(raw_pw=" " + PW, typ=PT + "PasswordText")), "deny")
check("Security 이름만 같고 다른 ns", *send(B["GetDeviceInformation"],
      '<x:Security s:mustUnderstand="1" xmlns:x="urn:x"><x:UsernameToken><x:Username>admin</x:Username></x:UsernameToken></x:Security>'), "mu")
check("모르는 필수 헤더 + 맞는 계정", *send(B["GetDeviceInformation"], tok() + '<x:Foo s:mustUnderstand="1" xmlns:x="urn:x"/>'), "mu")
# 깨진 XML 은 어떤 오류든 괜찮고 서버가 살아 있어야 한다
c, t = send("", raw='<s:Envelope xmlns:s="' + S12 + '"><s:Header>' + tok())
print(f"{'PASS' if c != 200 else 'FAIL'}  {'깨진 XML (닫는 태그 없음) → 오류':<52} 결과 {c}")
fails += c == 200
c, t = send("", raw="x" * 200000)
print(f"{'PASS' if c != 200 else 'FAIL'}  {'200KB 쓰레기 데이터 → 오류':<52} 결과 {c}")
fails += c == 200
pad = "<x:Pad xmlns:x='urn:x'>" + "A" * 70000 + "</x:Pad>"
check("70KB 헤더 뒤에 계정 (앞 64KB 만 봄)", *send(B["GetDeviceInformation"], pad + tok()), "deny")
s = socket.create_connection((HOST.split(":")[0], int(HOST.split(":")[1])), timeout=5)
s.send(b"POST /onvif/device_service HTTP/1.1\r\nHost: x\r\nContent-Length: 500\r\n\r\n<s:Env")
s.close()   # 보내다 끊김
ok = alive()
print(f"{'PASS' if ok else 'FAIL'}  {'요청 중간에 끊긴 뒤 서버 응답':<52} {'살아 있음' if ok else '응답 없음!'}")
fails += not ok

if a.lockout:
    print("\n== 5. 잠금 (5번 틀리면 60초)")
    for i in range(5):
        c, t = send(B["GetDeviceInformation"], tok(pw="bad" + str(i)))
    check("5번 틀린 뒤 맞는 계정 → 잠김", *send(B["GetDeviceInformation"], tok(digest=False)), "deny")
    check("잠긴 동안 로그인 전 조회는 허용", *send(B["GetSystemDateAndTime"]), "ok")
    print("     61초 기다림 ...")
    time.sleep(61)
    check("61초 뒤 맞는 계정 → 풀림", *send(B["GetDeviceInformation"], tok(digest=False)), "ok")

ok = alive()
print(f"\n서버 {'살아 있음' if ok else '응답 없음!'}")
fails += not ok
print(f"== {'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)
