#!/usr/bin/env python3
"""라이다 edge v1.0.1-lidar 설치 후 시험 (PC 에서).  python lidar_edge_test.py <IP>
서비스·버전, 센서망·라이다, 영상(my_camera=줌, detection_zoom), selfcheck, ONVIF 기능 시험(ft), 줌 구동, 끝나면 0,0.
"""
import io, json, os, re, subprocess, sys, time, paramiko
HERE = os.path.dirname(os.path.abspath(__file__))
FT = os.path.join(HERE, "onvif_function_test.py")
ip = sys.argv[1]
USER, PW = os.environ.get("LIDAR_USER", "poe"), os.environ.get("LIDAR_PASS", "")
S = f"echo '{PW}' | sudo -S -p '' "
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
for _ in range(60):
    try: c.connect(ip, username=USER, password=PW, timeout=8); break
    except Exception: time.sleep(5)
def sh(x, t=180):
    _, o, e = c.exec_command(x, timeout=t); return (o.read() + e.read()).decode("utf-8", "replace")
host = sh("hostname").strip()
D = os.path.join(os.environ.get("LIDAR_DATA", os.path.join(os.getcwd(), "data")), "lidar_test", f"{host}_edge_{time.strftime('%Y%m%d_%H%M')}"); os.makedirs(D, exist_ok=True)
up = float(sh("cut -d' ' -f1 /proc/uptime"))
if up < 150: print(f"부팅 {up:.0f}s - 서비스 안정 대기", flush=True); time.sleep(150 - up)
R = []; raw = {}
ONVIF_LOGIN = r'''import base64, hashlib, os, datetime, sys, urllib.request as U
# 장비 안에서: python3 onvif_login.py <비밀번호파일>  -> ONVIF GetDeviceInformation (admin, PasswordDigest)
pw = open(sys.argv[1]).read().strip()
n = os.urandom(16); c = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
d = base64.b64encode(hashlib.sha1(n + c.encode() + pw.encode()).digest()).decode()
sec = ('<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" '
       'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><wsse:UsernameToken>'
       '<wsse:Username>admin</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
       + d + '</wsse:Password><wsse:Nonce>' + base64.b64encode(n).decode() + '</wsse:Nonce><wsu:Created>' + c + '</wsu:Created></wsse:UsernameToken></wsse:Security>')
e = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Header>' + sec +
     '</s:Header><s:Body><GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>')
try:
    r = U.urlopen(U.Request('http://127.0.0.1:1000/onvif/device_service', e.encode(), {'Content-Type': 'application/soap+xml'}), timeout=5).read().decode()
    print('LOGIN', 'OK' if 'Manufacturer' in r else 'FAULT')
except Exception as ex:
    print('LOGIN ERR', getattr(ex, 'code', ex))
'''
def res(k, ok, d): R.append((k, "O" if ok is True else ("X" if ok is False else ok), d)); print(f"{R[-1][1]} {k:<24} {d}", flush=True)
SV = "edge-device-id mediamtx edge-settings edge-ptz edge-healthcheck edge-whep-bridge onvif_srvd wsdd redis-server".split()
st = dict(zip(SV, sh("systemctl is-active " + " ".join(SV)).split()))
res("서비스", all(v == "active" for v in st.values()), " ".join(f"{k}={v}" for k, v in st.items() if v != "active") or f"{len(SV)}개 active")
ver = sh("cat ~/edge/.sw_version; md5sum $(readlink -f /usr/local/bin/onvif_srvd) | cut -c1-8; cat /etc/pact-model; cat ~/edge/device_id.txt 2>/dev/null").split()
res("SW", ver[:2] == ["v1.0.1-lidar", "a8e37f1f"], f"edge {ver[0]} / onvif {ver[1]} / model {ver[2] if len(ver)>2 else '?'} / {ver[3] if len(ver)>3 else '-'}")
res("부팅 시 onvif 재시작", None if False else "기록", sh("journalctl -u onvif_srvd -b --no-pager -o cat | grep -c 'onvif_srvd starting'").strip() + "회")
net = sh("ip -br addr show br-sensor; ip -br link | grep -E 'eth1|eth2'; ls /etc/udev/rules.d/ | grep -c usb-lan; nmcli -t -f NAME con show | grep -c static-eth1")
res("센서망 br-sensor", "192.168.1.10/24" in net, " / ".join(l.strip() for l in net.splitlines()[:3]))
lid = sh("cd ~/cm5-setup && timeout 90 ./check_lidar.py 2>&1", 120); raw["lidar"] = lid
res("라이다", "[OK]" in (lid.strip().splitlines() or [""])[-1], (re.search(r"Points: \d+ \((\d+)/s", lid) or [None, "-"])[1] + " pts/s")
for p in ("my_camera", "detection_zoom"):
    o = sh(f"timeout 20 ffprobe -v error -rtsp_transport tcp -select_streams v:0 -show_entries stream=codec_name,width,height,avg_frame_rate -of csv=p=0 rtsp://127.0.0.1:8554/{p} 2>&1; "
           f"timeout 25 ffmpeg -hide_banner -loglevel error -stats -rtsp_transport tcp -t 5 -i rtsp://127.0.0.1:8554/{p} -f null - 2>&1 | tr '\r' '\n' | grep frame= | tail -1", 60)
    fr = int((re.search(r"frame=\s*(\d+)", o) or [0, 0])[1]); raw[p] = o
    res(f"영상 {p}", fr >= 50, f"{o.strip().splitlines()[0] if o.strip() else '-'} / 5초 {fr} frames")
o = sh(f"timeout 15 ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_name,width,height -of csv=p=0 rtsp://{ip}:8554/my_camera 2>&1"); raw["ext"] = o
res("영상 외부 인증 없이 (401 이어야)", "401" in o, f"rtsp://{ip}:8554/my_camera -> {o.strip()[:60]}")
WEBPW = os.environ.get("LIDAR_WEB_PASS")   # 웹에서 바꾼 비밀번호 (없으면 이 두 항목 건너뜀)
if WEBPW:
    import base64 as _b, urllib.parse as _q
    sf0 = c.open_sftp(); sf0.putfo(io.BytesIO(WEBPW.encode()), "/tmp/.wp"); sh("chmod 600 /tmp/.wp")
    sf0.putfo(io.BytesIO(ONVIF_LOGIN.encode()), "/tmp/onvif_login.py")
    lo = sh("python3 /tmp/onvif_login.py /tmp/.wp 2>/dev/null")
    res("ONVIF 로그인 (admin + 웹 비밀번호)", "LOGIN OK" in lo, lo.strip()[:60])
    o2 = sh(f"timeout 15 ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_name,width,height -of csv=p=0 "
            f"\"rtsp://admin:$(python3 -c 'import urllib.parse;print(urllib.parse.quote(open(\"/tmp/.wp\").read().strip(),safe=\"\"))')@{ip}:8554/my_camera\" 2>&1; rm -f /tmp/.wp")
    res("영상 외부 (admin + 웹 비밀번호)", "h264" in o2 or "hevc" in o2, o2.strip()[:60])
else:
    res("ONVIF 로그인·외부 영상 (웹 비밀번호)", "건너뜀", "LIDAR_WEB_PASS 없음")
sc = sh("cd ~/edge && timeout 120 python3 selfcheck.py 2>&1", 150); raw["selfcheck"] = sc
m = re.search(r"ok\D*(\d+).*?warn\D*(\d+).*?fail\D*(\d+)", sc.replace("\n", " "), re.S)
fails = [l.strip() for l in sc.splitlines() if re.search(r"\bfail\b|\[FAIL\]|✗|X ", l)][:8]
res("edge selfcheck", "기록", (m[0] if m else sc.strip().splitlines()[-1:] or ["-"])[0][:80] if True else "")
health = sh("journalctl -u edge-healthcheck -b --no-pager -o cat | grep INFO | tail -2"); raw["health"] = health
res("헬스체크", "기록", (health.strip().splitlines() or ["-"])[-1][-60:])
sf = c.open_sftp(); sf.putfo(io.BytesIO(open(FT, "rb").read()), "/tmp/ft.py")
fo = sh("python3 /tmp/ft.py 2>&1", 300); raw["ft"] = fo
for l in fo.splitlines():
    mm = re.match(r"([OX])\s+(\S.*?)\s{2,}(.*)", l)
    if mm: res("ONVIF " + mm[2], mm[1] == "O", mm[3])
zd = sh("curl -s -m 5 'http://127.0.0.1:7777/zoom?ratio=10' >/dev/null; sleep 6; curl -s -m 5 http://127.0.0.1:7777/status; echo; curl -s -m 5 'http://127.0.0.1:7777/zoom?ratio=1' >/dev/null; sleep 6; curl -s -m 5 http://127.0.0.1:7777/status")
raw["zoom_api"] = zd
res("줌 (edge ptz_api)", "기록", zd.replace("\n", " ")[:120])
# 0,0 (ONVIF)
z = sh("""python3 - <<'PY'
import sys; sys.argv=['x']
src=open('/tmp/ft.py').read().split('R=[]')[0]; exec(src)
mv(0,0); time.sleep(8); p,t,m,e=st(); print(f'ZERO {p*D:+.2f} {t*D:+.2f} {m}')
PY""", 60); raw["zero"] = z
mz = re.search(r"ZERO ([-+\d.]+) ([-+\d.]+)", z)
res("0,0 (ONVIF)", bool(mz) and abs(float(mz[1])) < 0.5, f"pan {mz[1]}° tilt {mz[2]}° (틸트 하한 펌웨어 값)" if mz else z[-100:])
c.close()
json.dump({"host": host, "ip": ip, "rows": R}, open(os.path.join(D, "result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in raw.items(): open(os.path.join(D, f"raw_{k}.txt"), "w", encoding="utf-8").write(v)
print("FAIL:", [r[0] for r in R if r[1] == "X"]); print("SAVED", D)
