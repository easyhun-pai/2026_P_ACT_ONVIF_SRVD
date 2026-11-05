#!/usr/bin/env python3
"""
ONVIF mk3-basic 배포 묶음 만들기 (Windows / Linux 공통, 인터넷 불필요)

  python3 tools/make_package.py --binary <빌드된 onvif_srvd>
      → dist/onvif_mk3_basic_<날짜>_<md5 앞 8자리>.zip   (저장소 최상위 dist/)
  바이너리는 저장소에 넣지 않는다 — 장비에서 빌드한 build/onvif_srvd 를 가져와 지정 (docs/BUILD.md)

묶음 구성
  device/onvif_srvd, device/onvif_start.sh   장비에 올릴 바이너리·시작 스크립트
  device/onvif_setup/                         장비 시험 도구 → /home/ptz/workspace/onvif_setup 에 설치
  device/INSTALL.txt                          설치·확인·원복 절차
  src/                                        소스 + mk3-basic.patch
  README.md, docs/                            설명·빌드·배포·운용 문서
"""
import argparse
import hashlib
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 저장소 최상위

FILES = {
    "device/onvif_start.sh": "deploy/onvif_start.sh",
    "device/onvif_setup/onvif_cam_view.py": "tools/onvif_setup/onvif_cam_view.py",
    "device/onvif_setup/onvif_pan_tilt.py": "tools/onvif_setup/onvif_pan_tilt.py",
    "device/onvif_setup/onvif_move.py": "tools/onvif_setup/onvif_move.py",
    "device/onvif_setup/onvif_zoom_test.py": "tools/onvif_setup/onvif_zoom_test.py",
    "device/onvif_setup/onvif_stream_test.py": "tools/onvif_setup/onvif_stream_test.py",
    "device/onvif_setup/onvif_wsse_test.py": "tools/onvif_setup/onvif_wsse_test.py",
    "device/onvif_setup/onvif_auth_test.py": "tools/onvif_setup/onvif_auth_test.py",
    "device/edge_onvif_auth_patch.py": "deploy/edge_onvif_auth_patch.py",
    "docs/VERSIONS.md": "docs/VERSIONS.md",
    "docs/PTZ_STREAMING.md": "docs/PTZ_STREAMING.md",
    "docs/WSSE.md": "docs/WSSE.md",
    "device/onvif_setup/README.txt": "tools/onvif_setup/README.txt",
    "src/ServicePTZ.cpp": "src/ServicePTZ.cpp",
    "src/onvif_srvd.cpp": "src/onvif_srvd.cpp",
    "src/CMakeLists.txt": "src/CMakeLists.txt",
    "src/mk3-basic.patch": "src/mk3-basic.patch",
    "README.md": "README.md",
    "docs/MK3_BASIC.md": "docs/MK3_BASIC.md",
    "docs/BUILD.md": "docs/BUILD.md",
    "docs/DEPLOY.md": "docs/DEPLOY.md",
    "docs/OPERATIONS.md": "docs/OPERATIONS.md",
    "docs/HARDWARE.md": "docs/HARDWARE.md",
}
EXEC = {"device/onvif_srvd", "device/onvif_start.sh",
        "device/onvif_setup/onvif_cam_view.py", "device/onvif_setup/onvif_pan_tilt.py",
        "device/onvif_setup/onvif_move.py", "device/onvif_setup/onvif_zoom_test.py",
        "device/onvif_setup/onvif_stream_test.py", "device/onvif_setup/onvif_wsse_test.py",
        "device/onvif_setup/onvif_auth_test.py", "device/edge_onvif_auth_patch.py"}

INSTALL_TXT = """ONVIF mk3-basic 장비 설치 (장비에서 실행, 인터넷 불필요)

binary md5: {md5}

  # 0) PC → 장비로 옮기고 풀기 (PC가 Windows / Ubuntu / macOS 무엇이든 같은 명령)
  #    PC:   scp onvif_mk3_basic_*.zip ptz@<장비IP>:~/
  #    장비: cd ~ && python3 -m zipfile -e onvif_mk3_basic_*.zip . && cd onvif_mk3_basic_*/device
  #    (zip을 Windows에서 풀어서 올리면 실행 권한이 빠지지만 아래 install/chmod가 다시 준다)

  # 1) 기존 것 백업
  B=/home/ptz/onvif_backup_$(date +%Y%m%d); sudo mkdir -p $B
  sudo cp -n /usr/local/bin/onvif_srvd $B/onvif_srvd.prev
  sudo cp -n /home/ptz/edge/onvif_start.sh $B/onvif_start.sh.prev
  sudo cp -n /home/ptz/edge/settings_handler.py $B/settings_handler.py.prev

  # 2) 교체 (이 폴더에서)
  sudo systemctl stop onvif_srvd
  sudo install -m 755 onvif_srvd /usr/local/bin/onvif_srvd
  sudo install -m 755 onvif_start.sh /home/ptz/edge/onvif_start.sh
  sudo systemctl start onvif_srvd

  # 2b) edge 패치 (ONVIF 계정 확인 v1.1 — 웹 비밀번호 변경 때 원문 파일도 씀)
  sudo python3 edge_onvif_auth_patch.py /home/ptz/edge/settings_handler.py && sudo systemctl restart edge-settings
  #     이미 웹 비밀번호를 정한 장비: 원문 파일을 한 번 만들어야 ODM·NVR(Digest)이 됨 (틀린 값이면 쓰이지 않음)
  #     sudo sh -c "umask 077; printf '%s' '<웹 비밀번호>' > /var/lib/onvif_srvd/onvif_auth"
  #     문제 시 확인 끄기: sudo touch /var/lib/onvif_srvd/onvif_auth_off

  # 3) 시험 도구 설치 → ~/workspace/onvif_setup
  mkdir -p /home/ptz/workspace/onvif_setup && cp -r onvif_setup/. /home/ptz/workspace/onvif_setup/
  chmod +x /home/ptz/workspace/onvif_setup/*.py

  # 4) 확인 — 재시작이므로 모터 명령 0건이어야 함 (모터가 켜진 상태라면)
  onvif_srvd --version
  sudo journalctl -u onvif_srvd -b | grep PTZ | tail
  onvif_srvd --mcu-watch          # Ctrl+C 종료
  python3 /home/ptz/workspace/onvif_setup/onvif_cam_view.py              # PC 브라우저 http://<장비IP>:8090
  python3 /home/ptz/workspace/onvif_setup/onvif_pan_tilt.py --quick      # 팬/틸트 시험 (약 1분)

  # 원복
  sudo systemctl stop onvif_srvd
  sudo install -m 755 $B/onvif_srvd.prev /usr/local/bin/onvif_srvd
  sudo install -m 755 $B/onvif_start.sh.prev /home/ptz/edge/onvif_start.sh
  sudo cp $B/settings_handler.py.prev /home/ptz/edge/settings_handler.py && sudo systemctl restart edge-settings
  sudo systemctl start onvif_srvd

주의: edge install.sh 는 바이너리와 onvif_start.sh 를 덮어쓴다.
"""


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="ONVIF mk3-basic deploy package (zip)")
    ap.add_argument("--binary", required=True, help="built onvif_srvd (aarch64) to include as device/onvif_srvd")
    a = ap.parse_args()
    if not os.path.isfile(a.binary):
        sys.exit(f"[ERROR] binary not found: {a.binary}")
    for dst, src in FILES.items():
        if not os.path.isfile(os.path.join(ROOT, src)):
            sys.exit(f"[ERROR] missing {src}")

    bmd5 = md5(a.binary)
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    name = f"onvif_mk3_basic_{time.strftime('%Y%m%d')}_{bmd5[:8]}"
    out = os.path.join(ROOT, "dist", name + ".zip")

    def add(z, arc, data=None, path=None):
        zi = zipfile.ZipInfo(f"{name}/{arc}", time.localtime()[:6])
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = ((0o755 if arc in EXEC else 0o644) | 0o100000) << 16
        if data is None:
            with open(path, "rb") as f:
                data = f.read()
        z.writestr(zi, data)

    with zipfile.ZipFile(out, "w") as z:
        for dst, src in FILES.items():
            add(z, dst, path=os.path.join(ROOT, src))
        add(z, "device/onvif_srvd", path=a.binary)
        add(z, "device/INSTALL.txt", data=INSTALL_TXT.format(md5=bmd5).encode("utf-8"))
    print(f"OK  {out}")
    print(f"    binary md5 {bmd5}, size {os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
