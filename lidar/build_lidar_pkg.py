"""edge v1.0.1 (Pro) -> 라이다용 패키지 v1.0.1-lidar 만들기 (PC 에서).
  python build_lidar_pkg.py <Pro v1.0.1 패키지 폴더>
  -> build/edge_v1.0.1-lidar/pkg/v1.0.1-lidar/ (+ pkg/bins/mediamtx), install_lidar.sh, README.md, 그리고 build/edge_v1.0.1-lidar.zip
패키지 폴더: edge-sw 서버의 v1.0.1/ 에서 받은 SHA256SUMS version.txt edge-sw.tar.gz device-ui.tar.gz onvif-deps.tar.gz kiosk.tar.gz
            + bins/mediamtx 를 mediamtx 로. 바꾸는 것은 README.md
"""
import hashlib, io, os, re, shutil, sys, tarfile

SRC = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
VER = "v1.0.1-lidar"
BUNDLE = os.path.join(os.getcwd(), "build", "edge_" + VER)
OUT = os.path.join(BUNDLE, "pkg", VER)
os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.join(BUNDLE, "pkg", "bins"), exist_ok=True)
log = []

def patch(name, data):
    t = data.decode("utf-8")
    o = t
    t = t.replace("/home/ptz", "/home/poe")
    if name == "./systemd/edge-whep-bridge.service":
        t = re.sub(r"^User=ptz$", "User=poe", t, flags=re.M); t = re.sub(r"^Group=ptz$", "Group=poe", t, flags=re.M)
    if name == "./updater.py":
        t = t.replace('EDGE_USER = "ptz"', 'EDGE_USER = "poe"')
    if name == "./platform_mqtt.py":
        t = t.replace('group: str = "ptz"', 'group: str = "poe"')
    if name == "./mediamtx.yml.template":
        new = ("  my_camera:\n"
               "    # 라이다: 광각(rpiCamera) 없음 -> 줌카메라 영상을 기본 영상으로 (ONVIF·WebRTC·녹화)\n"
               "    source: rtsp://__ZOOM_USER__:__ZOOM_PASS__@192.168.1.68/stream1\n"
               "    rtspTransport: tcp\n"
               "    record: yes\n")
        t2 = re.sub(r"  my_camera:\n    source: rpiCamera\n    record: yes\n", new, t)
        assert t2 != t, "my_camera block not found"; t = t2
    if name == "./settings_handler.py":
        t2 = t.replace('def _restore_rpi_camera():\n    """rpiCamera 소스를 복원하고 저장된 카메라 설정 적용"""\n',
                       'def _restore_rpi_camera():\n    """rpiCamera 소스를 복원하고 저장된 카메라 설정 적용"""\n'
                       '    if IS_LIDAR:\n        return   # 라이다: 광각 없음, my_camera 는 줌 RTSP 고정\n')
        assert t2 != t; t = t2
        t2 = t.replace('def start_pipeline() -> tuple[bool, str]:\n',
                       'def start_pipeline() -> tuple[bool, str]:\n'
                       '    if IS_LIDAR:\n        return False, "라이다 모델은 AI(광각) 파이프라인을 지원하지 않습니다"\n', 1)
        assert t2 != t; t = t2
        # 모듈 맨 앞 import 뒤에 모델 판정
        t2 = re.sub(r"(\nimport os\n)", r"\1IS_LIDAR = os.path.exists('/etc/pact-model') and open('/etc/pact-model').read().strip() == 'lidar'\n", t, count=1)
        assert t2 != t, "import os not found"; t = t2
    if name == "./selfcheck.py":
        t2 = re.sub(r"(\nimport os\n)", r"\1IS_LIDAR = os.path.exists('/etc/pact-model') and open('/etc/pact-model').read().strip() == 'lidar'\n", t, count=1)
        assert t2 != t; t = t2
        a = '    if e1["ip"] != "192.168.1.10":\n        add("줌카메라", "eth1", "fail",'
        assert a in t
        t = t.replace(a, '    if IS_LIDAR:   # 라이다: 줌·라이다가 br-sensor 브리지(eth1+eth2)에 붙는다\n'
                         '        _br = subprocess.run(["ip", "-4", "-br", "addr", "show", "br-sensor"], capture_output=True, text=True).stdout\n'
                         '        add("줌카메라", "센서망", "ok" if "192.168.1.10/" in _br else "fail",\n'
                         '            "br-sensor 192.168.1.10" if "192.168.1.10/" in _br else f"br-sensor 주소 이상: {_br.strip() or \'없음\'}")\n'
                         '    elif e1["ip"] != "192.168.1.10":\n        add("줌카메라", "eth1", "fail",', 1)
        b = '    hailo = os.path.exists("/dev/hailo0")\n    add("AI", "Hailo",'
        assert b in t
        t = t.replace(b, '    hailo = os.path.exists("/dev/hailo0") and not IS_LIDAR\n'
                         '    if IS_LIDAR:\n        add("AI", "Hailo", "skip", "라이다 모델 — AI 미사용")\n'
                         '    else:\n      add("AI", "Hailo",', 1)
    if t != o:
        log.append(name)
    return t.encode("utf-8")

src = tarfile.open(os.path.join(SRC, "edge-sw.tar.gz"))
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as dst:
    for m in src.getmembers():
        if m.isfile():
            d = src.extractfile(m).read()
            if m.name.endswith((".py", ".sh", ".service", ".template", "-restart", ".json", ".conf")) or "/systemd/" in m.name or m.name.endswith("onvif-restart"):
                try: d = patch(m.name, d)
                except UnicodeDecodeError: pass
            m.size = len(d); dst.addfile(m, io.BytesIO(d))
        else:
            dst.addfile(m)
open(os.path.join(OUT, "edge-sw.tar.gz"), "wb").write(buf.getvalue())
for f in ("device-ui.tar.gz", "onvif-deps.tar.gz", "kiosk.tar.gz"):
    shutil.copy(os.path.join(SRC, f), OUT)
open(os.path.join(OUT, "version.txt"), "w", newline="\n").write(VER + "\n")
shutil.copy(os.path.join(SRC, "mediamtx"), os.path.join(BUNDLE, "pkg", "bins", "mediamtx"))
with open(os.path.join(OUT, "SHA256SUMS"), "w", newline="\n") as f:
    for fn in ("edge-sw.tar.gz", "device-ui.tar.gz", "onvif-deps.tar.gz", "kiosk.tar.gz", "version.txt"):
        f.write(hashlib.sha256(open(os.path.join(OUT, fn), "rb").read()).hexdigest() + "  " + fn + "\n")
shutil.copy(os.path.join(HERE, "install_lidar.sh"), BUNDLE); shutil.copy(os.path.join(HERE, "README.md"), BUNDLE)
shutil.make_archive(BUNDLE, "zip", os.path.dirname(BUNDLE), os.path.basename(BUNDLE))
print("patched:", len(log)); print("\n".join(log)); print("zip:", BUNDLE + ".zip")
