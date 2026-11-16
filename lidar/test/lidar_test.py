#!/usr/bin/env python3
"""P.act Lidar 출고 전 시험 - PC 에서.  python lidar_test.py <IP>
라이다 1차 시험 가이드 v1.0 항목 + Pro 11-13 모터 시험(끝단 발열·떨림) + 끝나면 팬·틸트 0,0.
모터: V/I/E/Q/T/S 만 (설정 바꾸는 명령 없음). 결과 -> ./data/lidar_test/<host>_<시각>/ (LIDAR_DATA 로 바꿈)
"""
import io, json, os, re, socket, subprocess, sys, time
import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.join(HERE, "motor_check_dev.py")
OUTB = os.path.join(os.environ.get("LIDAR_DATA", os.path.join(os.getcwd(), "data")), "lidar_test")
ip = sys.argv[1]
USER, PW = os.environ.get("LIDAR_USER", "poe"), os.environ.get("LIDAR_PASS", "")
S = f"echo '{PW}' | sudo -S -p '' "

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(ip, username=USER, password=PW, timeout=10)
def sh(x, t=120):
    _, o, e = c.exec_command(x, timeout=t); return (o.read() + e.read()).decode("utf-8", "replace")

R, raw = {}, {}
R["ping"] = "O" if subprocess.run(["ping", "-n", "2", ip], capture_output=True).returncode == 0 else "X"
R["SSH 접속"] = "O"
host = sh("hostname").strip()
D = os.path.join(OUTB, f"{host}_{time.strftime('%Y%m%d_%H%M')}"); os.makedirs(D, exist_ok=True)
print(f"[{host}] {ip}", flush=True)

# 1. 정보 (가이드 올인원과 같은 항목)
info = sh(r"""echo "NAME=$(hostname)"; echo "MAC=$(cat /sys/class/net/eth0/address)"; echo "OS=$(grep PRETTY /etc/os-release | cut -d'"' -f2)";
echo "SW=$(md5sum /usr/local/bin/onvif_srvd 2>/dev/null | cut -c1-8 | grep . || echo -)"; echo "LAN=$(lsusb | grep -cE '0bda:815[23]')";
echo "ZT=$(""" + S + r"""zerotier-cli status 2>&1 | head -1)"; echo "NET=$(ip -br addr show br-sensor | awk '{print $1, $3}')"; echo "SSHEN=$(systemctl is-enabled ssh 2>&1)";
echo "HW=$(tr -d '\000' < /proc/device-tree/model)"; echo "UPTIME=$(uptime -p)"; """ + S + "systemctl stop edge-lidar-stream onvif_srvd 2>/dev/null; true")
raw["info"] = info
I = dict(l.split("=", 1) for l in info.splitlines() if "=" in l and l.split("=", 1)[0].isupper())
R["SSH 자동실행"] = "O" if I.get("SSHEN") == "enabled" else "X"
zt = I.get("ZT", "")
R["ZeroTier 설치"] = "O" if "ONLINE" in zt or "OFFLINE" in zt or zt.startswith("200") else "X"
print("  info", {k: I.get(k) for k in ("MAC", "OS", "SW", "LAN", "ZT", "NET")}, flush=True)

# 2. 라이다
lid = sh("cd ~/cm5-setup && timeout 90 ./check_lidar.py 2>&1", 120); raw["lidar"] = lid
R["라이다"] = "O" if "[OK]" in lid.strip().splitlines()[-1:][0] else "X"
bc = (re.search(r"broadcast code (\w+)", lid) or [None, "-"])[1]
pts = (re.search(r"Points: \d+ \(([\d]+)/s", lid) or [None, "-"])[1]
print("  lidar", R["라이다"], bc, pts, flush=True)

# 3. 줌 영상 + 4. 줌 구동
zs = sh(r"""URL=$(grep -o 'rtsp://[^ "]*' ~/cm5-setup/run_zoomcamera.sh); timeout 20 ffprobe -v error -rtsp_transport tcp -select_streams v:0 -show_entries stream=codec_name,width,height,avg_frame_rate -of csv=p=0 "$URL"; echo ===; timeout 30 ffmpeg -hide_banner -loglevel error -stats -rtsp_transport tcp -t 5 -i "$URL" -f null - 2>&1 | tr '\r' '\n' | grep frame= | tail -1""", 90)
raw["zoom_stream"] = zs
fr = int((re.search(r"frame=\s*(\d+)", zs) or [0, 0])[1])
zprobe = zs.split("===")[0].strip()
ZD = r"""python3 - <<'PY'
import re,time,urllib.request as U,urllib.parse as P
sh=open('/home/poe/cm5-setup/run_zoomcamera.sh').read()
u=re.search(r'rtsp://([^:]+):([^@]+)@([^/]+)',sh)
user,pw,host=u[1],P.unquote(u[2]),u[3]; url=f'http://{host}/onvif/ptz_service'
pm=U.HTTPPasswordMgrWithDefaultRealm(); pm.add_password(None,url,user,pw)
op=U.build_opener(U.HTTPDigestAuthHandler(pm))
NS=('xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"')
H={'Content-Type':'application/soap+xml'}
def env(b): return '<?xml version="1.0"?><s:Envelope '+NS+'><s:Body>'+b+'</s:Body></s:Envelope>'
def soap(b): return op.open(U.Request(url,env(b).encode(),H),timeout=5).read().decode()
T='<tptz:ProfileToken>ONFProfileToken_101</tptz:ProfileToken>'
R=r'Position>.*?Zoom[^>]*x="([\d.]+)"'
def zoom(): return float(re.search(R,soap('<tptz:GetStatus>'+T+'</tptz:GetStatus>'),re.S)[1])
def pos(x): return f'<tptz:Position><tt:Zoom x="{x}"/></tptz:Position>'
def move(x): soap('<tptz:AbsoluteMove>'+T+pos(x)+'</tptz:AbsoluteMove>'); time.sleep(6); return zoom()
a=zoom(); b=move(1.0); c=move(0.0); ok='OK' if b>0.95 and c<0.05 else 'X'
print(f'ZOOM start {a:.2f} -> x10 {b:.2f} -> x1 {c:.2f} :', ok)
PY"""
zd = sh(ZD, 60); raw["zoom_drive"] = zd
zok = ": OK" in zd
R["run_zoomcamera"] = "O" if (fr >= 120 and zok) else "X"
print("  zoom", zprobe, "frames", fr, zd.strip()[-60:], flush=True)

# 5. 모터 (Pro 와 같은 motor_check_dev: V I E Q, 팬 양 끝 발열, 틸트 위·아래 발열, 떨림)
sf = c.open_sftp(); sf.putfo(io.BytesIO(open(DEV, "rb").read()), "/tmp/motor_check_dev.py")
mo = sh(S + "python3 /tmp/motor_check_dev.py '{}' 2>&1", 300); raw["motor"] = mo
M = json.loads(mo.split("RESULT ", 1)[1].strip().splitlines()[0]) if "RESULT " in mo else {}
p, t = M.get("pan", {}), M.get("tilt", {})
def hh(ax, i):
    try: h = ax["holds"][i]; return f"{h['cur']:+.3f} rad {h['heat']:.2f} W"
    except Exception: return "-"
ends_ok = all(not ax.get("error") and ax.get("holds") and all(h and abs(h["cur"] - max(min(h["target"], ax["max"]), ax["min"])) < 0.05 for h in ax["holds"]) for ax in (p, t))
R["pantilt"] = "O" if ends_ok else "X"

# 6. 0,0
z = r"""import sys
sys.argv=["x"]
exec(open("/tmp/motor_check_dev.py").read().split("res = {}")[0])
for name, port in (("pan", "/dev/ttyAMA0"), ("tilt", "/dev/ttyAMA2")):
    fd = open_port(port); st = q(fd)
    if st and not (st["flags"] & 1): cmd(fd, "S", 2.0); time.sleep(1)
    cmd(fd, "T0", 0.3); time.sleep(4); e = q(fd)
    print(f"ZERO {name} {e['cur']:+.3f} {e['heat']:.2f}")
    os.close(fd)
"""
sf.putfo(io.BytesIO(z.encode()), "/tmp/zero.py")
zo = sh(S + "python3 /tmp/zero.py", 60); raw["zero"] = zo
Z = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(r"ZERO (\w+) ([-+\d.]+) ([\d.]+)", zo)}
c.close()

fw = f"PAN {p.get('V', '?')} / TILT {t.get('V', '?')}"
mx = lambda ax: max([h["heat"] for h in ax.get("holds", []) if h] or [0])
wob = max([w["pp_deg"] or 0 for w in p.get("wobble", []) + t.get("wobble", [])] or [0])
S_ = dict(host=host, ip=ip, mac=I.get("MAC"), os=I.get("OS"), hw=I.get("HW"), sw=I.get("SW"), zt=zt, net=I.get("NET"), lan=I.get("LAN"),
          fw=fw, lidar_code=bc, lidar_pts=pts, zoom_probe=zprobe, zoom_frames=fr, zoom_drive=zd.strip(),
          pan_range=[p.get("min"), p.get("max")], tilt_range=[t.get("min"), t.get("max")], pan_P=p.get("vel_p"), offset=[p.get("offset"), t.get("offset")],
          pan_minus=hh(p, 0), pan_plus=hh(p, 1), tilt_top=hh(t, 0), tilt_145=hh(t, 1), tilt_bottom=hh(t, 2), wobble_max_deg=wob,
          flags=[(p.get("q1") or {}).get("flags"), (t.get("q1") or {}).get("flags")], trips=[(p.get("q1") or {}).get("trips"), (t.get("q1") or {}).get("trips")],
          zero=Z, checklist=R, date=time.strftime("%Y-%m-%d"))
json.dump(S_, open(os.path.join(D, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in raw.items(): open(os.path.join(D, f"raw_{k}.txt"), "w", encoding="utf-8").write(v)
print(json.dumps(S_, ensure_ascii=False, indent=1))
print("SAVED", D)
