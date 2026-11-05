#!/usr/bin/env python3
"""WS-Security 헤더 허용 시험 (장비에서, onvif 켠 채로). 모터는 움직이지 않는다 (조회만).

  python3 onvif_wsse_test.py [HOST:PORT]     기본 127.0.0.1:1000

- 헤더 없음 / wsse:Security(mustUnderstand=1, Digest·Text, 접두사 여러 가지, wsa 같이) -> 200 이어야 PASS
- 모르는 mustUnderstand 헤더 -> 500 MustUnderstand 그대로여야 PASS (SOAP 규칙 유지)
- 응답에 보낸 계정·비밀번호가 되돌아오면 FAIL
"""
import base64
import datetime
import hashlib
import os
import sys
import urllib.error
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:1000"
URL = f"http://{HOST}/onvif/device_service"
S12 = "http://www.w3.org/2003/05/soap-envelope"
S11 = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PT = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#"
USER, PASS = "probeuser", "probe-secret-123"

OPS = {
    "GetDeviceInformation": '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>',
    "GetProfiles": '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>',
    "GetStreamUri": ('<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl"><StreamSetup>'
                     '<Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>'
                     '<Transport xmlns="http://www.onvif.org/ver10/schema"><Protocol>RTSP</Protocol></Transport>'
                     '</StreamSetup><ProfileToken>{tok}</ProfileToken></GetStreamUri>'),
    "PTZ GetStatus": ('<GetStatus xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
                      '<ProfileToken>MainStream</ProfileToken></GetStatus>'),
}


def token(env_pfx, pfx="wsse", digest=True, ns=WSSE):
    nonce = os.urandom(16)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if digest:
        pw = base64.b64encode(hashlib.sha1(nonce + created.encode() + PASS.encode()).digest()).decode()
        ptype = PT + "PasswordDigest"
    else:
        pw, ptype = PASS, PT + "PasswordText"
    return (f'<{pfx}:Security {env_pfx}:mustUnderstand="1" xmlns:{pfx}="{ns}" xmlns:wsu="{WSU}">'
            f'<{pfx}:UsernameToken><{pfx}:Username>{USER}</{pfx}:Username>'
            f'<{pfx}:Password Type="{ptype}">{pw}</{pfx}:Password>'
            f'<{pfx}:Nonce>{base64.b64encode(nonce).decode()}</{pfx}:Nonce>'
            f'<wsu:Created>{created}</wsu:Created></{pfx}:UsernameToken></{pfx}:Security>')


def send(body, header="", soap11=False):
    ns, ct = (S11, "text/xml; charset=utf-8") if soap11 else (S12, "application/soap+xml; charset=utf-8")
    env = (f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="{ns}">'
           f'{"<s:Header>" + header + "</s:Header>" if header else ""}<s:Body>{body}</s:Body></s:Envelope>')
    req = urllib.request.Request(URL, data=env.encode(), headers={"Content-Type": ct})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


CASES = [
    # name, header builder, soap11, expected status
    ("헤더 없음", lambda: "", False, 200),
    ("wsse Digest (ODM 형태)", lambda: token("s"), False, 200),
    ("wsse Text", lambda: token("s", digest=False), False, 200),
    ("wsse 접두사 o (WCF)", lambda: token("s", pfx="o"), False, 200),
    ("wsse + wsa Action/To", lambda: token("s") +
        '<a:Action s:mustUnderstand="1" xmlns:a="http://www.w3.org/2005/08/addressing">x</a:Action>'
        f'<a:To s:mustUnderstand="1" xmlns:a="http://www.w3.org/2005/08/addressing">{URL}</a:To>', False, 200),
    ("SOAP 1.1 + wsse", lambda: token("s"), True, 200),
    ("모르는 헤더 (mustUnderstand 없음)", lambda: '<x:Foo xmlns:x="urn:x">1</x:Foo>', False, 200),
    ("모르는 헤더 mustUnderstand=1", lambda: '<x:Foo s:mustUnderstand="1" xmlns:x="urn:x">1</x:Foo>', False, 500),
    ("Security 이름만 같고 다른 ns", lambda: '<x:Security s:mustUnderstand="1" xmlns:x="urn:x">1</x:Security>', False, 500),
]

import re
_, _r = send(OPS["GetProfiles"])
_m = re.search(r'Profiles[^>]*token="([^"]+)"', _r)
OPS["GetStreamUri"] = OPS["GetStreamUri"].replace("{tok}", _m[1] if _m else "MainStream")
print(f"profile token: {_m[1] if _m else '?'}")

fails = 0
for name, hdr, s11, want in CASES:
    for op, body in OPS.items():
        if s11 and op != "GetDeviceInformation":
            continue
        code, txt = send(body, hdr(), s11)
        leak = PASS in txt or USER in txt
        mu = "MustUnderstand" in txt
        ok = code == want and not leak and (mu if want == 500 else True)
        fails += not ok
        note = " (응답에 계정 노출!)" if leak else (" MustUnderstand" if mu else "")
        uri = re.search(r'<tt:Uri>([^<]*)', txt) if op == "GetStreamUri" and code == 200 else None
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} {op:<22} {code}{note}{'  ' + uri[1] if uri else ''}")
print(f"\n== {'ALL PASS' if not fails else f'{fails} FAIL'}")
sys.exit(1 if fails else 0)
