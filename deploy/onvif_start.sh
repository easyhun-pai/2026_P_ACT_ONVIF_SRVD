#!/bin/bash
# ONVIF 서버 시작 스크립트
# 기본 라우팅 경로의 src IP와 인터페이스를 동적 감지 (다중 NIC 환경 대응)

# 1순위: 기본 라우트 src IP (실제 outbound에 사용되는 IP)
ROUTE_INFO=$(ip route get 1.1.1.1 2>/dev/null)
IP=$(echo "$ROUTE_INFO" | grep -oP 'src \K[\d.]+' | head -1)
IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K\S+' | head -1)

# 2순위: eth0
if [ -z "$IP" ]; then
    IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet )\d+\.\d+\.\d+\.\d+' | head -1)
    IFACE="eth0"
fi

# 3순위: 첫 번째 non-loopback IP — 내부 카메라망(eth1, br-sensor)은 제외
#   (2026-11-02) eth0이 DHCP를 못 받으면 예전엔 eth1의 192.168.1.10을 집어 외부에서 접근 불가한
#   주소로 떴다. 인터페이스 이름도 실제 IP와 맞게 짝짓는다.
if [ -z "$IP" ]; then
    read -r IFACE IP < <(ip -4 -o addr show scope global 2>/dev/null |
        awk '$2 != "eth1" && $2 !~ /^br-sensor/ { split($4, a, "/"); print $2, a[1]; exit }')
fi

[ -z "$IP" ] && IP="127.0.0.1"
[ -z "$IFACE" ] && IFACE="eth0"

# --detect: 감지한 IP만 출력 (90-onvif-restart가 IP 변경 여부 비교에 사용)
if [ "$1" = "--detect" ]; then echo "$IP"; exit 0; fi

# 이번 실행에 사용한 IP 기록 — 같은 IP면 dispatcher가 재시작하지 않음
# (재시작마다 모터 MCU에 R/S 초기화가 나가서 부팅 시 모터가 들썩/떨림)
echo "$IP" > /run/onvif_srvd.ip

# 플랫폼 PTZ 자세 보고(telemetry/<id>/ptz) 브로커 — 운영 모드를 따른다 (v1.0)
#   online : 다른 서비스와 같은 플랫폼 브로커 (기존 기본값 <platform-broker-ip> 은 사내망에서만 동작)
#   offline: 장비 자신(로컬 브로커 없음) → 클라우드로 보내지 않음
#   2026-10-29: 모드와 상관없이 플랫폼으로 보내지 않는다 — onvif_srvd 는 MQTT 계정을 지원하지 않아
#   브로커가 익명을 막으면 끊긴다. 자세 보고는 설정 서버가 1초 간격으로 대신 보낸다 (settings_handler
#   _ptz_telemetry_loop). onvif_srvd 의 MQTT 는 보내기만 하고 명령은 받지 않으므로 PTZ 제어에는 영향 없음.
#   오프라인 모드에서 쓰던 설정(127.0.0.1, 로컬 브로커 없음)과 같다.
MODE=$(python3 -c 'import json;print((json.load(open("/home/ptz/edge/settings.json")).get("system") or {}).get("mode","online"))' 2>/dev/null || echo online)
export MQTT_BROKER=127.0.0.1

echo "onvif_srvd starting: IP=${IP} IFACE=${IFACE} MQTT_BROKER=${MQTT_BROKER} (mode=${MODE})"
exec /home/ptz/onvif_srvd \
    --ifs "$IFACE" \
    --name JetsonPTZ \
    --width 1280 \
    --height 720 \
    --url "rtsp://${IP}:8554/my_camera" \
    --type H264 \
    --scope onvif://www.onvif.org/Profile/Streaming \
    --ptz --no_fork --no_close
