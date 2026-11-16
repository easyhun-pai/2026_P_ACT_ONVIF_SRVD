#!/bin/bash
#===============================================================================
# P.ACT Lidar Edge SW 설치 스크립트 (v1.0.1-lidar = Pro v1.0.1 + 라이다 패치, 저장소 lidar/build_lidar_pkg.py)
#
# 사용법:
#   curl -fsSL https://<edge-sw-server>/firmware/edge-sw/<버전>/install.sh | bash
#   bash install.sh [버전]               예) bash install.sh v1.0.0-rc1
#   bash install.sh --version <버전>
#   bash install.sh --check [버전]     다운로드·sha256 확인만 하고 종료 (장비 변경 없음)
#   버전을 생략하면 이 파일이 빌드된 버전(PKG_VERSION)을 설치한다.
#
# 환경변수 (선택):
#   ZOOM_USER / ZOOM_PASS           줌카메라 계정 (RTSP·ONVIF 공용) ┐ 신규 설치 때만 사용.
#   TURN_PASSWORD                   TURN 공유 비밀값                ┘ 업그레이드는 기존 값 유지
#   SECRETS_FILE                    위 값을 KEY=VALUE 로 담은 파일 (기본 /home/ptz/.edge-secrets)
#   KIOSK=0                         HDMI 콘솔 잠금(키오스크) 설치 건너뜀
#   UNLOCK_PW                       키오스크 유지보수 비밀번호 (없으면 터미널에서 입력받음)
#   MODEL_EXTRA                     추가로 받을 Hailo 모델 (예: yolov11m.hef)
#   MINIO_BASE                      다운로드 주소 변경 (테스트용)
#
# 업그레이드 시 그대로 두는 것:
#   settings.json, device_id.txt, .device_auth, .jwt_secret(로그인 토큰 서명 키), .mqtt_account(플랫폼 MQTT 출입증), .device_key(플랫폼 터널 장비 열쇠), mediamtx.yml(줌카메라 계정·TURN 포함),
#   static-eth1 프로파일(값이 틀어졌으면 192.168.1.10/24 로 복구만 함), 키오스크(같은 버전이면)
#===============================================================================

# 파이프(curl | bash)로 실행돼도 스크립트 전체를 읽은 뒤 실행되도록 main() 으로 감싼다
# (다운로드가 끊긴 반쪽 스크립트 실행 방지, 하위 명령이 stdin 을 읽어 스크립트를 먹는 것 방지)
main() {
set -e

PKG_VERSION="v1.0.1-lidar"      # tools/build_package.sh 가 치환
# 패키지 위치: 이 스크립트 옆 pkg/ (묶음을 풀어서 실행), 없으면 /home/poe/edge_pkg
_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
if [ -z "$MINIO_BASE" ]; then
    if [ -f "$_SELF_DIR/pkg/v1.0.1-lidar/SHA256SUMS" ]; then MINIO_BASE="file://$_SELF_DIR/pkg"; else MINIO_BASE="file:///home/poe/edge_pkg"; fi
fi
MODEL_BASE="https://<edge-sw-server>/models/hailo"
MODEL_DEFAULT="yolov11s.hef"   # 기본 모델 (변경: yolov11m.hef, yolov11l.hef, yolov8n.hef)
EDGE_USER="poe"
EDGE_MODEL="lidar"   # 라이다: 광각·AI·키오스크·eth1 단계 없음, 줌 영상이 my_camera
KIOSK="${KIOSK:-0}"
EDGE_HOME="/home/$EDGE_USER"
EDGE_DIR="$EDGE_HOME/edge"
TMP_DIR="/tmp/edge-install-$$"
SECRETS_FILE="${SECRETS_FILE:-$EDGE_HOME/.edge-secrets}"
# 라이다: 줌카메라 계정을 제작사 스크립트(~/cm5-setup/run_zoomcamera.sh 의 RTSP 주소)에서 읽는다 (직접 주면 그 값)
if [ -z "$ZOOM_USER" ] && [ -f "$EDGE_HOME/cm5-setup/run_zoomcamera.sh" ]; then
    _zu=$(grep -o 'rtsp://[^:/"]*:[^@"]*@' "$EDGE_HOME/cm5-setup/run_zoomcamera.sh" | head -1)
    if [ -n "$_zu" ]; then
        ZOOM_USER=$(echo "$_zu" | sed -E 's#rtsp://([^:]*):.*#\1#')
        ZOOM_PASS=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.unquote(sys.argv[1]))' "$(echo "$_zu" | sed -E 's#rtsp://[^:]*:(.*)@#\1#')")
    fi
fi
NEED_REBOOT=0
NEW_DEVICE=0
# 일반 계정 SSH 의 PATH 에는 /usr/sbin 이 없어 dkms 를 못 찾고 Hailo 드라이버 패치를 건너뛰었다 (2026-11-03 ptz010)
case ":$PATH:" in *:/usr/sbin:*) ;; *) PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin" ;; esac

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

VERSION=""
CHECK_ONLY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --check)     CHECK_ONLY=1; shift ;;
        --version)   VERSION="$2"; shift 2 ;;
        --version=*) VERSION="${1#*=}"; shift ;;
        *)           VERSION="$1"; shift ;;
    esac
done
if [ -z "$VERSION" ]; then
    case "$PKG_VERSION" in
        __*) log_error "설치할 버전을 지정하세요: bash install.sh v1.0.0-rc1"; exit 1 ;;
        *)   VERSION="$PKG_VERSION" ;;
    esac
fi

id "$EDGE_USER" >/dev/null 2>&1 || { log_error "사용자 $EDGE_USER 가 없습니다"; exit 1; }
HAVE_TTY=0
if [ -r /dev/tty ] && (exec </dev/tty) 2>/dev/null; then HAVE_TTY=1; fi

# 장치 IP 감지 (eth0 우선, 없으면 wlan0)
DEVICE_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
[ -n "$DEVICE_IP" ] || DEVICE_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
[ -n "$DEVICE_IP" ] || DEVICE_IP=$(hostname -I | awk '{print $1}')
log_info "버전: $VERSION   장치 IP: $DEVICE_IP"

#-------------------------------------------------------------------------------
# 1. 다운로드 + 무결성 확인
#-------------------------------------------------------------------------------
log_info "다운로드: $MINIO_BASE/$VERSION/"
mkdir -p "$TMP_DIR"
cd "$TMP_DIR"
for f in SHA256SUMS version.txt edge-sw.tar.gz device-ui.tar.gz onvif-deps.tar.gz kiosk.tar.gz; do
    if ! curl -fsSL --retry 3 "$MINIO_BASE/$VERSION/$f" -o "$f"; then
        log_error "다운로드 실패: $MINIO_BASE/$VERSION/$f"
        exit 1
    fi
done
# install.sh 자신은 파이프로 받았을 수 있으므로 검사 대상에서 제외
if ! grep -v '  install\.sh$' SHA256SUMS | sha256sum -c --quiet -; then
    log_error "sha256 불일치 — 파일이 손상됐거나 다른 버전이 섞였습니다. 설치 중단"
    exit 1
fi
log_info "다운로드·sha256 확인 완료 ($(cat version.txt))"
if [ "$CHECK_ONLY" = 1 ]; then
    cd / && rm -rf "$TMP_DIR"
    log_info "--check: 확인만 하고 종료 (장비 변경 없음)"
    exit 0
fi

echo "$EDGE_MODEL" | sudo tee /etc/pact-model >/dev/null
log_info "모델: $EDGE_MODEL (/etc/pact-model)"

#-------------------------------------------------------------------------------
# 2. 기존 설치 백업 + 압축 해제
#-------------------------------------------------------------------------------
if [ -f "$EDGE_DIR/settings_handler.py" ]; then
    BACKUP="$EDGE_HOME/edge-preinstall-$(date +%Y%m%d-%H%M%S).tgz"
    if sudo tar czf "$BACKUP" -C "$EDGE_HOME" --exclude='edge/device-ui-dist.new' --exclude='edge/__pycache__' edge 2>/dev/null; then
        sudo chmod 600 "$BACKUP"   # mediamtx.yml 계정 정보가 들어 있음
        log_info "기존 설치 백업: $BACKUP"
        # 백업은 최근 3개만 유지 (원격 업데이트 실패 시 updater.py 가 가장 최근 것으로 되돌림)
        ls -1t "$EDGE_HOME"/edge-preinstall-*.tgz 2>/dev/null | tail -n +4 | xargs -r sudo rm -f
    else
        log_warn "기존 설치 백업 실패 — 계속 진행"
    fi
fi

log_info "edge-sw 압축 해제 → $EDGE_DIR"
sudo mkdir -p "$EDGE_DIR"
sudo tar -xzf edge-sw.tar.gz -C "$EDGE_DIR" --no-same-owner
# 제품에서 빠진 모듈은 이전 설치의 잔재를 지운다 (tar 는 덮어쓰기만 하므로). 화재·연기 감지: rc13 에서 제거.
sudo rm -f "$EDGE_DIR/fire_detector.py"

log_info "device-ui 교체 → $EDGE_DIR/device-ui-dist"
sudo rm -rf "$EDGE_DIR/device-ui-dist.new"
sudo mkdir -p "$EDGE_DIR/device-ui-dist.new"
sudo tar -xzf device-ui.tar.gz -C "$EDGE_DIR/device-ui-dist.new" --no-same-owner
sudo rm -rf "$EDGE_DIR/device-ui-dist"
sudo mv "$EDGE_DIR/device-ui-dist.new" "$EDGE_DIR/device-ui-dist"

#-------------------------------------------------------------------------------
# 3. 소유권 및 실행 권한
#    서비스 계정(ptz)이 설정 저장, mediamtx.yml 갱신 등을 할 수 있어야 한다.
#-------------------------------------------------------------------------------
sudo chown -R "$EDGE_USER:$EDGE_USER" "$EDGE_DIR"
chmod +x "$EDGE_DIR"/*.sh "$EDGE_DIR"/*.py "$EDGE_DIR"/network/*.sh "$EDGE_DIR"/tools/*.sh 2>/dev/null || true
cp version.txt "$EDGE_DIR/.sw_version"

# 파이프라인 스크립트 심볼릭 링크 (구버전 settings_handler 호환)
ln -sf "$EDGE_DIR/wide_detection_fixed.sh" "$EDGE_HOME/wide_detection_fixed.sh"

# 현장 점검 스크립트
install -m 755 "$EDGE_DIR/tools/site_check.sh" "$EDGE_HOME/site_check.sh"
log_info "현장 점검 스크립트: $EDGE_HOME/site_check.sh"

#-------------------------------------------------------------------------------
# 4. mediamtx.yml — 기존 파일이 있으면 그대로(계정·TURN 값 보존), 없으면 템플릿으로 생성
#-------------------------------------------------------------------------------
MTX="$EDGE_DIR/mediamtx.yml"
if [ -f "$MTX" ] && ! grep -q '__ZOOM_USER__\|__ZOOM_PASS__\|__TURN_PASSWORD__' "$MTX"; then
    log_info "mediamtx.yml 기존 파일 유지 (줌카메라 계정·TURN 값 보존)"
else
    log_info "mediamtx.yml 생성 (신규 설치)"
    NEW_DEVICE=1
    if [ -f "$SECRETS_FILE" ]; then
        log_info "  계정 정보 파일 사용: $SECRETS_FILE"
        for k in ZOOM_USER ZOOM_PASS TURN_PASSWORD; do
            if [ -z "${!k}" ]; then
                v=$(grep -m1 "^$k=" "$SECRETS_FILE" | cut -d= -f2- || true)
                [ -n "$v" ] && printf -v "$k" '%s' "$v"
            fi
        done
    fi
    if [ "$HAVE_TTY" = 1 ]; then
        [ -n "$ZOOM_USER" ]     || read -r  -p "  줌카메라 사용자명: " ZOOM_USER </dev/tty
        [ -n "$ZOOM_PASS" ]     || { read -r -s -p "  줌카메라 비밀번호: " ZOOM_PASS </dev/tty; echo; }
        [ -n "$TURN_PASSWORD" ] || { read -r -s -p "  TURN 공유 비밀값 (모르면 Enter): " TURN_PASSWORD </dev/tty; echo; }
    fi
    export ZOOM_USER ZOOM_PASS TURN_PASSWORD
    python3 - "$EDGE_DIR/mediamtx.yml.template" "$MTX" <<'PY'
import json, os, sys
from urllib.parse import quote
src, dst = sys.argv[1], sys.argv[2]
txt = open(src, encoding="utf-8").read()
# 줌카메라 계정은 RTSP URL 안에 들어가므로 URL 인코딩, TURN 값은 YAML 문자열로
for key, enc in (("ZOOM_USER", lambda v: quote(v, safe="")), ("ZOOM_PASS", lambda v: quote(v, safe="")),
                 ("TURN_PASSWORD", json.dumps)):
    val = os.environ.get(key) or ""
    if val:
        txt = txt.replace(f"__{key}__", enc(val))
open(dst, "w", encoding="utf-8").write(txt)
os.chmod(dst, 0o640)
PY
    if grep -q '__ZOOM_USER__\|__ZOOM_PASS__' "$MTX"; then
        log_warn "  줌카메라 계정 미입력 — 줌 영상(detection_zoom)과 줌 제어가 동작하지 않습니다."
        log_warn "  나중에 넣는 법: $SECRETS_FILE 에 ZOOM_USER=..., ZOOM_PASS=... 작성 후 $MTX 삭제하고 install.sh 재실행"
    fi
    if grep -q '__TURN_PASSWORD__' "$MTX"; then
        log_warn "  TURN 값 미입력 — 같은 망이 아닌 곳에서 원격 영상이 안 될 수 있습니다."
    fi
fi
# 기존 파일에도 적용하는 보정: Control API(9997)는 장비 안에서만 받는다.
# 이전 버전은 모든 인터페이스에 열려 있고 관리자 항목 ips 가 비어 있어, 같은 망의 누구나
# 설정·경로(줌카메라 계정 포함)를 읽고 바꿀 수 있었다. 재생(9996)·HLS(8888)는 현장에서 쓰므로 그대로.
python3 - "$MTX" <<'PY'
import re, sys
p = sys.argv[1]
txt = open(p, encoding="utf-8").read()
new = re.sub(r"^apiAddress: :9997\s*$", "apiAddress: 127.0.0.1:9997", txt, flags=re.M)
# authInternalUsers 중 'action: api' 가 있는 항목(관리자)의 빈 ips 만 localhost 로 제한
def fix_admin(m):
    block = m.group(0)
    if "action: api" in block:
        block = re.sub(r"^(\s+ips:) \[\]\s*$", r"\1 ['127.0.0.1', '::1']", block, count=1, flags=re.M)
    return block
new = re.sub(r"^- user: .*?(?=^- user: |^[A-Za-z#])", fix_admin, new, flags=re.M | re.S)
if new != txt:
    open(p, "w", encoding="utf-8").write(new)
    print("  mediamtx.yml 보정: Control API localhost 고정")
PY
sudo chown "$EDGE_USER:$EDGE_USER" "$MTX"

#-------------------------------------------------------------------------------
# 5. Hailo AI 런타임 (미설치 시에만)
#    hailo-all: HailoRT + TAPPAS Core + GStreamer + OpenCV (~422MB, 초기 1회)
#-------------------------------------------------------------------------------
if [ "$EDGE_MODEL" = "lidar" ]; then
    log_info "라이다: Hailo AI 런타임 설치 건너뜀 (광각 AI 없음)"
elif ! command -v hailortcli &>/dev/null; then
    log_info "Hailo AI 런타임 설치 (최초 1회, ~422MB)"
    # apt 캐시 완전 재생성 후 설치 (신규 장비 apt index 불완전 대비)
    sudo rm -rf /var/lib/apt/lists/*
    sudo apt-get update -qq </dev/null 2>/dev/null || true
    if sudo DEBIAN_FRONTEND=noninteractive apt-get install -y hailo-all gstreamer1.0-rtsp gstreamer1.0-plugins-ugly gstreamer1.0-plugins-bad libhiredis0.14 </dev/null 2>/dev/null; then
        log_info "  Hailo AI 런타임 설치 완료 — 재부팅 후 활성화됩니다"
        NEED_REBOOT=1
    else
        log_warn "  Hailo 설치 실패 — AI 기능 비활성화됨"
    fi
else
    log_info "Hailo AI 런타임 이미 설치됨 — 건너뜀"
    # GStreamer RTSP 플러그인 보완 (구버전 장비 호환)
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gstreamer1.0-rtsp gstreamer1.0-plugins-ugly libhiredis0.14 </dev/null 2>/dev/null || true
fi

# TAPPAS 커스텀 post-process 라이브러리 (libredis_export.so 등)
TAPPAS_POSTPROC="/usr/lib/aarch64-linux-gnu/hailo/tappas/post_processes"
if [ -d "$TAPPAS_POSTPROC" ]; then
    log_info "TAPPAS post-process 라이브러리 배포"
    if curl -fsSL "$MINIO_BASE/bins/tappas-postproc.tar.gz" -o "$TMP_DIR/tappas-postproc.tar.gz" 2>/dev/null && \
       sudo tar -xzf "$TMP_DIR/tappas-postproc.tar.gz" -C / --no-same-owner 2>/dev/null; then
        log_info "  tappas-postproc 설치 완료"
    else
        log_warn "  tappas-postproc 설치 실패"
    fi
fi

# Hailo PCIe 드라이버 4.20.0 패치 — 커널 6.12 에서 AI 가 도는 동안 커널 경고(find_vma)가 초당 백여 건
# 쌓여 시스템 로그가 30분 만에 밀려나는 문제. hailort-drivers master 와 같은 수정이며 재부팅 후 반영된다.
# 이미 적용됐는지 먼저 보고(두 번 적용 방지), 소스가 예상과 다르면 건너뛴다(-F0: 어긋남 허용 안 함).
HAILO_SRC=/usr/src/hailo_pci-4.20.0
HAILO_PATCH="$EDGE_DIR/patches/hailo_pci-4.20.0-find_vma-mmap-lock.patch"
if [ -f "$HAILO_SRC/linux/vdma/memory.c" ] && [ -f "$HAILO_PATCH" ]; then
    if ! command -v patch >/dev/null || ! command -v dkms >/dev/null; then
        log_warn "Hailo 드라이버 패치 건너뜀 (patch 또는 dkms 없음)"
    elif sudo patch -p1 -R -F0 -f -s --dry-run -d "$HAILO_SRC" < "$HAILO_PATCH" >/dev/null 2>&1; then
        log_info "Hailo 드라이버 패치 이미 적용됨"
    elif [ ! -d "/lib/modules/$(uname -r)/build" ]; then
        log_warn "Hailo 드라이버 패치 건너뜀 (커널 헤더 없음)"
    elif sudo patch -p1 -F0 -f -s --dry-run -d "$HAILO_SRC" < "$HAILO_PATCH" >/dev/null 2>&1 && \
         sudo cp -p "$HAILO_SRC/linux/vdma/memory.c" "$HAILO_SRC/linux/vdma/memory.c.pact-orig" && \
         sudo patch -p1 -F0 -f -s -d "$HAILO_SRC" < "$HAILO_PATCH" >/dev/null 2>&1; then
        log_info "Hailo 드라이버 패치 적용 — 다시 빌드"
        if sudo dkms build -m hailo_pci -v 4.20.0 --force </dev/null >"$TMP_DIR/dkms.log" 2>&1 && \
           sudo dkms install -m hailo_pci -v 4.20.0 --force </dev/null >>"$TMP_DIR/dkms.log" 2>&1; then
            log_info "  Hailo 드라이버 빌드 완료 — 재부팅 후 반영"
            NEED_REBOOT=1
        else
            sudo cp -p "$HAILO_SRC/linux/vdma/memory.c.pact-orig" "$HAILO_SRC/linux/vdma/memory.c" || true
            log_warn "  Hailo 드라이버 빌드 실패 — 원래 소스로 되돌림 (AI 는 기존 드라이버로 동작): $(tail -1 "$TMP_DIR/dkms.log")"
        fi
    else
        log_warn "Hailo 드라이버 소스가 예상과 달라 패치 건너뜀"
    fi
fi

#-------------------------------------------------------------------------------
# 6. ONVIF/PTZ 의존성 (onvif_srvd, wsdd, libgsoap, libmosquitto 번들)
#-------------------------------------------------------------------------------
log_info "ONVIF 의존성 설치"
sudo tar -xzf "$TMP_DIR/onvif-deps.tar.gz" -C / --no-same-owner
sudo chmod +x /usr/local/bin/onvif_srvd /usr/local/bin/wsdd 2>/dev/null || true
sudo ldconfig

# IP 변경(DHCP 갱신 / 재연결) 시 onvif_srvd + wsdd 가 새 IP로 재시작되도록 훅 설치
NM_HOOK_DIR="/etc/NetworkManager/dispatcher.d"
if [ -d "$NM_HOOK_DIR" ] && [ -f "$EDGE_DIR/nm-onvif-restart" ]; then
    sudo install -m 755 -o root -g root "$EDGE_DIR/nm-onvif-restart" "$NM_HOOK_DIR/90-onvif-restart"
    log_info "  NM dispatcher 훅: $NM_HOOK_DIR/90-onvif-restart"
fi
DHCPCD_HOOK_DIR="/lib/dhcpcd/dhcpcd-hooks"
if [ -d "$DHCPCD_HOOK_DIR" ] && [ -f "$EDGE_DIR/dhcpcd-onvif-restart" ]; then
    sudo install -m 755 -o root -g root "$EDGE_DIR/dhcpcd-onvif-restart" "$DHCPCD_HOOK_DIR/90-onvif-restart"
    log_info "  dhcpcd 훅: $DHCPCD_HOOK_DIR/90-onvif-restart"
fi

#-------------------------------------------------------------------------------
# 7. 줌카메라 LAN (eth1 = 192.168.1.10/24, 게이트웨이 없음)
#    신규 장비: network/configure_eth1.sh (어댑터 이름 고정 + static-eth1 생성)
#    기존 장비: static-eth1 이 틀어져 있으면(예: DHCP 로 바뀜) 값만 복구
#-------------------------------------------------------------------------------
if [ "$EDGE_MODEL" = "lidar" ]; then
    log_info "라이다: eth1 설정 건너뜀 (센서망 br-sensor $(ip -4 -br addr show br-sensor 2>/dev/null | awk '{print $3}') 그대로)"
elif command -v nmcli >/dev/null 2>&1; then
    if nmcli -t -f NAME connection show | grep -Fxq static-eth1; then
        cur="$(nmcli -g ipv4.method,ipv4.addresses,ipv4.gateway,connection.interface-name connection show static-eth1 | paste -sd'|')"
        if [ "$cur" = "manual|192.168.1.10/24||eth1" ]; then
            log_info "eth1(static-eth1) 정상 — 그대로 둠"
        else
            log_warn "static-eth1 값이 바뀌어 있음 ($cur) — 192.168.1.10/24 로 복구"
            sudo nmcli connection modify static-eth1 connection.interface-name eth1 \
                ipv4.method manual ipv4.addresses 192.168.1.10/24 ipv4.gateway "" ipv4.never-default yes
            sudo nmcli connection up static-eth1 </dev/null >/dev/null 2>&1 || log_warn "  static-eth1 활성화 실패 (eth1 케이블 확인)"
        fi
    else
        log_info "eth1(줌카메라 LAN) 최초 설정"
        sudo bash "$EDGE_DIR/network/configure_eth1.sh" </dev/null || log_warn "  eth1 설정 실패 — 수동: sudo bash $EDGE_DIR/network/configure_eth1.sh"
    fi
else
    log_warn "nmcli 없음 — eth1 설정 건너뜀"
fi

#-------------------------------------------------------------------------------
# 8. Redis 서버 (파이프라인/settings_handler 의존)
#-------------------------------------------------------------------------------
_install_redis_deb() {
    log_info "  redis deb 다운로드 (MinIO fallback)"
    local tmpd="$TMP_DIR/redis-debs"
    mkdir -p "$tmpd"
    for d in liblzf1 libjemalloc2 redis-tools redis-server; do
        curl -fsSL "$MINIO_BASE/bins/$d.deb" -o "$tmpd/$d.deb" 2>/dev/null || true
    done
    sudo dpkg --purge redis-server redis-tools </dev/null 2>/dev/null || true
    sudo dpkg -i "$tmpd/liblzf1.deb" "$tmpd/libjemalloc2.deb" \
                 "$tmpd/redis-tools.deb" "$tmpd/redis-server.deb" </dev/null 2>/dev/null || true
    command -v redis-server &>/dev/null && log_info "  redis-server (deb) 설치 완료" || \
        log_warn "  redis-server deb 설치 실패"
}

if ! command -v redis-cli &>/dev/null; then
    log_info "redis-server 설치"
    sudo apt-get update -qq </dev/null 2>/dev/null || true
    if ! sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq redis-server </dev/null 2>/dev/null; then
        _install_redis_deb
    fi
fi
if command -v redis-server &>/dev/null; then
    if ! systemctl is-active --quiet redis-server 2>/dev/null; then
        sudo systemctl enable redis-server 2>/dev/null || true
        sudo systemctl start redis-server 2>/dev/null && log_info "  redis-server 시작" || log_warn "  redis-server 시작 실패"
    fi
else
    log_warn "  redis-server 미설치 — 파이프라인(AI) 기능 비활성화됨"
fi

#-------------------------------------------------------------------------------
# 9. Python 패키지
#-------------------------------------------------------------------------------
log_info "필수 Python 패키지 설치"
PACKAGES="paho-mqtt redis requests websockets psutil"
# 라이다(Debian 13 trixie): pip 는 시스템 패키지 보호로 막힌다 -> apt 로
if [ "$EDGE_MODEL" = "lidar" ]; then
    _PYPK="python3-paho-mqtt python3-redis python3-requests python3-websockets python3-psutil"
    _apt_py() { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq -o DPkg::Lock::Timeout=180 $_PYPK </dev/null >>"$TMP_DIR/apt_py.log" 2>&1; }
    if _apt_py || { sudo apt-get update -qq </dev/null >/dev/null 2>&1; _apt_py; }; then
        log_info "  python3 패키지 apt 설치 완료"
    else
        log_warn "  python3 패키지 apt 설치 실패: $(tail -1 "$TMP_DIR/apt_py.log")"
    fi
    PACKAGES=""
fi
# ptz 유저 환경에 설치 (서비스 실행 경로 일치)
[ -z "$PACKAGES" ] || sudo -u "$EDGE_USER" pip3 install --quiet --break-system-packages $PACKAGES </dev/null 2>/dev/null || \
sudo -u "$EDGE_USER" pip3 install --quiet $PACKAGES </dev/null 2>/dev/null || \
sudo pip3 install --quiet --break-system-packages $PACKAGES </dev/null 2>/dev/null || \
    log_warn "pip 설치 실패 — 수동: sudo -u $EDGE_USER pip3 install $PACKAGES"
# 플랫폼 터널 장비 열쇠(tunnel_auth.py)용. Raspberry Pi OS 에는 기본으로 있다 — 없을 때만 설치
if ! python3 -c "import cryptography.hazmat.primitives.asymmetric.ed25519" 2>/dev/null; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-cryptography </dev/null 2>/dev/null ||         log_warn "python3-cryptography 설치 실패 — 장비 열쇠 없이 터널 접속 (플랫폼 MQTT 출입증 못 받음)"
fi

#-------------------------------------------------------------------------------
# 10. mediamtx 바이너리 + systemd 서비스
#-------------------------------------------------------------------------------
if [ ! -f /usr/local/bin/mediamtx ]; then
    log_info "mediamtx 바이너리 다운로드"
    if curl -fsSL "$MINIO_BASE/bins/mediamtx" -o "$TMP_DIR/mediamtx"; then
        sudo install -m 755 "$TMP_DIR/mediamtx" /usr/local/bin/mediamtx
        log_info "  mediamtx 설치 완료"
    else
        log_warn "  mediamtx 다운로드 실패 — 수동 설치 필요"
    fi
fi
sudo mkdir -p /opt/mediamtx
if [ ! -e /opt/mediamtx/mediamtx ] && [ -f /usr/local/bin/mediamtx ]; then
    sudo ln -sf /usr/local/bin/mediamtx /opt/mediamtx/mediamtx
fi
sudo install -m 640 -o root -g "$EDGE_USER" "$MTX" /opt/mediamtx/mediamtx.yml

# onvif_srvd 경로 보정 (/home/ptz/onvif_srvd → /usr/local/bin/onvif_srvd)
if [ -f /usr/local/bin/onvif_srvd ] && [ ! -L "$EDGE_HOME/onvif_srvd" ]; then
    [ -f "$EDGE_HOME/onvif_srvd" ] && sudo mv "$EDGE_HOME/onvif_srvd" "$EDGE_HOME/onvif_srvd.old"
    sudo ln -sf /usr/local/bin/onvif_srvd "$EDGE_HOME/onvif_srvd"
fi

# mediamtx 는 edge-settings 보다 먼저 재시작한다. edge-settings 가 시작하며 my_camera 를 publisher 로 바꾸고
# 파이프라인을 띄우는데, 그 뒤에 mediamtx 가 재시작되면 설정 파일대로 rpiCamera 가 카메라를 다시 잡아
# 파이프라인이 카메라를 못 열고 크래시 감지(30초)까지 영상이 끊긴다.
SERVICES="edge-device-id mediamtx edge-settings edge-ptz edge-healthcheck edge-whep-bridge onvif_srvd wsdd wide-watchdog"
[ "$EDGE_MODEL" = "lidar" ] && SERVICES="edge-device-id mediamtx edge-settings edge-ptz edge-healthcheck edge-whep-bridge onvif_srvd wsdd"
log_info "systemd 서비스 파일 설치"
for svc in $SERVICES; do
    src="$EDGE_DIR/systemd/$svc.service"
    if [ ! -f "$src" ]; then log_warn "  서비스 파일 없음: $src"; continue; fi
    sed "s/__DEVICE_IP__/$DEVICE_IP/g" "$src" | sudo tee "/etc/systemd/system/$svc.service" > /dev/null
done

#-------------------------------------------------------------------------------
# 11. settings.json (없을 때만 생성 — 기존 설정은 그대로)
#-------------------------------------------------------------------------------
if [ ! -f "$EDGE_DIR/settings.json" ]; then
    log_info "settings.json 생성"
    cat > "$EDGE_DIR/settings.json" << 'SETTINGS_EOF'
{
  "stream": {"width": 1920, "height": 1080, "fps": 15, "bitrate": 5000000, "hflip": false, "vflip": false},
  "camera": {"brightness": 0, "contrast": 1, "saturation": 1, "sharpness": 1,
              "exposure_mode": "normal", "awb_mode": "auto", "denoise": "off",
              "hdr": false, "metering": "centre", "gain": 0, "ev": 0, "shutter": 0},
  "ai": {"enabled": false},
  "tracking": {"enabled": false},
  "ptz": {"mount_mode": "stand"},
  "mount_mode": "stand",
  "people_count": {"enabled": false, "region": {"points": []}},
  "output": {"mqtt": {"enabled": false}, "webhooks": []},
  "system": {"mode": "online"}
}
SETTINGS_EOF
    sudo chown "$EDGE_USER:$EDGE_USER" "$EDGE_DIR/settings.json"
fi
MODE=$(python3 -c "import json;print((json.load(open('$EDGE_DIR/settings.json')).get('system') or {}).get('mode','online'))" 2>/dev/null || echo online)

#-------------------------------------------------------------------------------
# 12. 서비스 시작
#-------------------------------------------------------------------------------
# onvif_srvd stale PID 파일 제거 (크래시 루프 방지)
sudo systemctl stop onvif_srvd 2>/dev/null || true
sudo pkill -9 -f onvif_srvd 2>/dev/null || true
rm -f "$EDGE_HOME/onvif_srvd.pid"

# 시스템 로그: 재부팅 후에도 유지, 상한 500MB (기본 상한은 디스크의 10% — 29GB 에서 약 3GB)
JD_DROPIN=/etc/systemd/journald.conf.d/pact-edge.conf
if ! grep -q "^SystemMaxUse=500M" "$JD_DROPIN" 2>/dev/null; then
    sudo mkdir -p "$(dirname "$JD_DROPIN")"
    printf '[Journal]\nStorage=persistent\nSystemMaxUse=500M\n' | sudo tee "$JD_DROPIN" > /dev/null
    sudo systemctl restart systemd-journald 2>/dev/null || true
    sudo journalctl --vacuum-size=500M > /dev/null 2>&1 || true
    log_info "시스템 로그 상한 500MB"
fi

sudo systemctl daemon-reload
for svc in $SERVICES; do
    sudo systemctl enable "$svc" 2>/dev/null || true
    if sudo systemctl restart "$svc" 2>/dev/null; then
        log_info "  시작: $svc"
    else
        log_warn "  실패: $svc (로그: journalctl -u $svc)"
    fi
done

#-------------------------------------------------------------------------------
# 12-1. 신규 장비: 줌카메라 기본값 (FHD 15fps, 영상 조정 공장 출하값) — Web UI Zoom 탭 "초기화"와 같음
#-------------------------------------------------------------------------------
if [ "$NEW_DEVICE" = 1 ] && ! grep -q '__ZOOM_USER__\|__ZOOM_PASS__' "$MTX"; then
    log_info "줌카메라 기본값 적용 (1920x1080 15fps)"
    sleep 3   # eth1 활성화 대기
    if zout=$(cd "$EDGE_DIR" && sudo python3 -c "import zoom_camera as z; z.apply_defaults(False)" </dev/null 2>&1); then
        log_info "  줌카메라 기본값 적용 완료"
    else
        log_warn "  줌카메라 기본값 적용 실패: $(echo "$zout" | tail -1)"
        log_warn "  Web UI > Camera Settings > Zoom > 초기화 로 다시 적용하세요"
    fi
fi

#-------------------------------------------------------------------------------
# 13. 플랫폼 등록 (오프라인 모드면 건너뜀)
#-------------------------------------------------------------------------------
if [ "$MODE" = "offline" ]; then
    log_info "오프라인 모드 — 플랫폼 등록 건너뜀"
else
    log_info "플랫폼 등록"
    sleep 2  # edge-device-id 서비스가 device_id 파일을 만들 시간
    (cd "$EDGE_DIR" && python3 device_register.py </dev/null) && log_info "  플랫폼 등록 완료" || \
        log_warn "  플랫폼 등록 실패 — 수동: cd $EDGE_DIR && python3 device_register.py"
fi

#-------------------------------------------------------------------------------
# 14. Hailo 모델 (없을 때만 기본 모델)
#-------------------------------------------------------------------------------
MODELS_DIR="$EDGE_HOME/models"
mkdir -p "$MODELS_DIR"
if [ "$EDGE_MODEL" = "lidar" ]; then
    :
elif [ ! -f "$MODELS_DIR/$MODEL_DEFAULT" ]; then
    log_info "Hailo 모델 다운로드: $MODEL_DEFAULT"
    curl -fsSL "$MODEL_BASE/$MODEL_DEFAULT" -o "$MODELS_DIR/$MODEL_DEFAULT" && log_info "  저장: $MODELS_DIR/$MODEL_DEFAULT" || \
        log_warn "  모델 다운로드 실패 — 수동으로 $MODELS_DIR 에 .hef 파일을 복사하세요"
fi
if [ -n "$MODEL_EXTRA" ]; then
    log_info "추가 모델 다운로드: $MODEL_EXTRA"
    curl -fsSL "$MODEL_BASE/$MODEL_EXTRA" -o "$MODELS_DIR/$MODEL_EXTRA" && log_info "  저장: $MODELS_DIR/$MODEL_EXTRA" || \
        log_warn "  추가 모델 다운로드 실패"
fi

#-------------------------------------------------------------------------------
# 15. HDMI 콘솔 잠금(키오스크) — 같은 버전이 이미 설치돼 있으면 건너뜀
#-------------------------------------------------------------------------------
if [ "${KIOSK:-1}" = "0" ]; then
    log_info "키오스크 설치 건너뜀 (KIOSK=0)"
else
    mkdir -p "$TMP_DIR/kiosk"
    tar -xzf "$TMP_DIR/kiosk.tar.gz" -C "$TMP_DIR/kiosk"
    k_new=$(cat "$TMP_DIR/kiosk/VERSION" 2>/dev/null || echo "?")
    k_cur=$(cat /opt/pact-kiosk/VERSION 2>/dev/null || echo "")
    if [ "$k_new" = "$k_cur" ] && systemctl is-enabled --quiet edge-splash 2>/dev/null; then
        log_info "키오스크 $k_cur 이미 설치됨 — 건너뜀"
    else
        log_info "키오스크 설치 ($k_cur → $k_new) — 재부팅 후 HDMI 로그인 차단"
        if sudo bash "$TMP_DIR/kiosk/install_splash.sh" </dev/null; then
            NEED_REBOOT=1
        else
            log_warn "  키오스크 설치 실패 — 수동: sudo bash /opt/pact-kiosk/install_splash.sh"
        fi
    fi
    if [ -f /opt/pact-kiosk/pact_splash.py ] && ! sudo test -s /etc/pact-kiosk/unlock.hash; then
        if [ -z "$UNLOCK_PW" ] && [ "$HAVE_TTY" = 1 ]; then
            read -r -s -p "  키오스크 유지보수 비밀번호 (Ctrl+Alt+Shift+P 해제용, 6자 이상, 건너뛰려면 Enter): " UNLOCK_PW </dev/tty; echo
        fi
        if [ -n "$UNLOCK_PW" ]; then
            printf '%s' "$UNLOCK_PW" | sudo python3 /opt/pact-kiosk/pact_splash.py --set-password && \
                log_info "  유지보수 비밀번호 설정됨" || log_warn "  유지보수 비밀번호 설정 실패"
        else
            log_warn "  유지보수 비밀번호 미설정 — HDMI 단축키 해제 불가 (설정: sudo bash /opt/pact-kiosk/install_splash.sh --set-password)"
        fi
    fi
fi

#-------------------------------------------------------------------------------
# 정리 (설치 캐시도 비움 — 받은 .deb 파일, 수백 MB)
#-------------------------------------------------------------------------------
sudo apt-get clean </dev/null > /dev/null 2>&1 || true
cd /
rm -rf "$TMP_DIR"

echo ""
echo "=============================================="
log_info "설치 완료!"
echo "  설치 경로: $EDGE_DIR"
echo "  장치 IP:   $DEVICE_IP"
echo "  버전:      $(cat "$EDGE_DIR/.sw_version")"
echo "  운영 모드: $MODE"
echo ""
echo "  현장 점검: bash $EDGE_HOME/site_check.sh"
if [ "$NEED_REBOOT" = "1" ]; then
    echo ""
    # 원격 업데이트(updater 의 edge-update 작업) 중이면 서비스 확인·완료 보고가 끝날 시간을 두고 스스로 재부팅.
    # 예약은 여기서 한다 — 업데이트를 실행하는 updater 는 장비에 깔려 있던 옛 버전일 수 있다.
    if grep -q "edge-update" /proc/self/cgroup 2>/dev/null && [ "${EDGE_UPDATE_NO_REBOOT:-0}" != "1" ] && \
       sudo systemd-run --on-active=60 --unit=edge-update-reboot --quiet systemctl reboot 2>/dev/null; then
        log_warn "재부팅이 필요합니다 (Hailo 드라이버 또는 키오스크 적용) — 업데이트 완료 후 60초 뒤 자동 재부팅"
    else
        log_warn "재부팅이 필요합니다 (Hailo 드라이버 또는 키오스크 적용): sudo reboot"
    fi
fi
echo "=============================================="
}

main "$@"
