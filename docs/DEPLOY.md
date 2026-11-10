# 배포 · 롤백 (mk3-basic)

## ⚠️ 운영 규칙

**운영 카메라에는 담당자의 명시적 지시 없이 배포·재시작하지 않는다.**

과거 운영 fleet 에 일괄 배포했다가 한 대에서 pan FOC 폭주가 발생했고,
복구 과정에서 정상 카메라까지 되돌려 피해를 키운 적이 있다.
**한 대에 대한 승인은 다른 대나 다음 단계로 확장되지 않는다.**

- 개발/실험은 시험용 장비(예: ptz018)에서
- 운영 대상 작업은 매번 개별 승인
- 배포는 한 대씩, 검증 후 다음 대
- **edge 패키지 업데이트(`install.sh`)는 `/usr/local/bin/onvif_srvd` 와 `/home/ptz/edge/onvif_start.sh` 를 덮어쓴다.**
  정식 반영은 edge 패키지에 넣어야 한다.
  install.sh 는 `<edge 배포 서버>/<버전>/onvif-deps.tar.gz` 를 `/` 에 풀며, 이 묶음의 onvif_srvd 가 현장 원본(448443)이다
  (2026-11-03 rc18 설치 때 ptz018 의 mk3-basic 이 원본으로 되돌아감). onvif-deps 의 `usr/local/bin/onvif_srvd` 를 교체해야 한다.

### v1.0.0 (ONVIF 계정 확인) 배포 때
- **밖에서 계정 없이 ONVIF 를 쓰던 클라이언트는 거부된다** (NVR 에 계정 없이 등록한 경우 등). 장비 안(edge 웹·플랫폼 PTZ)은 그대로.
- **edge 패치 같이**: `sudo python3 edge_onvif_auth_patch.py /home/ptz/edge/settings_handler.py && sudo systemctl restart edge-settings`
  (묶음 device/ 에 있음, 원본 백업 후). 웹 비밀번호를 바꿀 때 `/var/lib/onvif_srvd/onvif_auth` 에 원문을 쓴다.
- **이미 웹 비밀번호를 정한 장비**는 원문 파일이 없어 ODM·NVR(Digest)이 거부된다 → 둘 중 하나
  - 웹에서 비밀번호를 한 번 바꿨다가 되돌리기 (edge 패치 뒤)
  - 또는 `sudo sh -c "umask 077; printf '%s' '<웹 비밀번호>' > /var/lib/onvif_srvd/onvif_auth"` (틀린 값이면 쓰이지 않음)
- 문제가 생기면 `sudo touch /var/lib/onvif_srvd/onvif_auth_off` → 바로 v1.0 처럼 확인 안 함

## 배포 묶음 (권장)

빌드한 장비/PC 에서:

```bash
python3 tools/make_package.py --binary build/onvif_srvd
# → dist/onvif_mk3_basic_<날짜>_<md5 앞 8자리>.zip  (약 2 MB)
```

| 묶음 안 | 내용 |
|---|---|
| `device/onvif_srvd`, `device/onvif_start.sh` | 장비에 올릴 바이너리·시작 스크립트 |
| `device/onvif_setup/` | 장비 시험 도구 → `/home/ptz/workspace/onvif_setup` |
| `device/INSTALL.txt` | 아래 절차와 같은 설치·확인·원복 명령 (바이너리 md5 포함) |
| `src/`, `docs/`, `README.md` | 소스·문서 |

PC 운영체제와 무관하게 같은 명령으로 옮기고 푼다 (Windows 10+/Ubuntu/macOS 의 기본 `scp`, 장비의 `python3`).

```bash
# PC
scp onvif_mk3_basic_*.zip ptz@<장비IP>:~/
# 장비
cd ~ && python3 -m zipfile -e onvif_mk3_basic_*.zip . && cd onvif_mk3_basic_*/device
```

## 설치 (장비에서, 위 device/ 폴더)

```bash
# 1) 사전 기록
systemctl is-active onvif_srvd
md5sum /usr/local/bin/onvif_srvd
readlink -f /home/ptz/onvif_srvd             # 심볼릭 링크면 실제 대상 확인

# 2) 백업
B=/home/ptz/onvif_backup_$(date +%Y%m%d); sudo mkdir -p $B
sudo cp -n /usr/local/bin/onvif_srvd $B/onvif_srvd.prev
sudo cp -n /home/ptz/edge/onvif_start.sh $B/onvif_start.sh.prev

# 3) 교체 — 멈춘 뒤 install (실행 중 덮어쓰기는 Text file busy)
sudo systemctl stop onvif_srvd
sudo install -m 755 onvif_srvd /usr/local/bin/onvif_srvd
sudo install -m 755 onvif_start.sh /home/ptz/edge/onvif_start.sh
sudo systemctl start onvif_srvd

# 4) 시험 도구
mkdir -p /home/ptz/workspace/onvif_setup && cp -r onvif_setup/. /home/ptz/workspace/onvif_setup/
chmod +x /home/ptz/workspace/onvif_setup/*.py
```

`onvif_srvd stop` 은 모터에 아무 명령도 보내지 않는다 — 자세는 그대로 유지된다.
일부 유닛은 `/home/<user>/onvif_srvd` 가 `/usr/local/bin/onvif_srvd` 로 가는 링크다. **실제 파일(링크 대상)** 을 교체한다.

## 확인

```bash
onvif_srvd --version
sudo journalctl -u onvif_srvd -b | grep -E 'PTZ(-CMD|-ALERT)?:' | tail
onvif_srvd --mcu-watch                         # Ctrl+C 종료
```

모터가 이미 켜진 상태에서 교체했다면 재시작이므로 **모터 명령 0건**이어야 한다:

```
PTZ: boot power-on (rsts=0x1000), repeat start this boot
PTZ: pan firmware=v2.3.0-manual state=armed (target -0.27, current -0.27, offset 5.680)
PTZ-CMD: pan none - already armed, keep target -0.270
PTZ-CMD: tilt none - already armed, keep target 1.180
PTZ: ready (mk3-basic ...)
```

동작 시험 (onvif 를 켠 채로, 장비에서):

```bash
python3 ~/workspace/onvif_setup/onvif_cam_view.py       # PC 브라우저 http://<장비IP>:8090 — 광각/줌 OK
python3 ~/workspace/onvif_setup/onvif_pan_tilt.py --quick   # 약 25초, VERDICT: PASS
```

ONVIF 응답 확인 (어느 PC 에서나):

```bash
python3 - <<'EOF'
import urllib.request
IP = "<ptz018-ip>"
body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        '<s:Body><GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>')
req = urllib.request.Request(f"http://{IP}:1000/onvif/device_service", data=body.encode(),
                             headers={"Content-Type": "application/soap+xml; charset=utf-8"})
print("OK" if "GetDeviceInformationResponse" in urllib.request.urlopen(req, timeout=8).read().decode() else "NG")
EOF
```

## 롤백

```bash
B=/home/ptz/onvif_backup_<날짜>
sudo systemctl stop onvif_srvd
sudo install -m 755 $B/onvif_srvd.prev /usr/local/bin/onvif_srvd
sudo install -m 755 $B/onvif_start.sh.prev /home/ptz/edge/onvif_start.sh
sudo systemctl start onvif_srvd
```

## 긴급 정지 (모터 이상 동작 시)

순서를 지킬 것. **onvif 만 멈춰서는 토크가 안 풀린다.**

```bash
# 1) 서비스 정지 + 자동시작 해제 (부팅 시 재발 방지)
sudo systemctl stop onvif_srvd.service
sudo systemctl disable onvif_srvd.service
#    NetworkManager dispatcher 가 네트워크 이벤트 때 onvif 를 다시 띄우지 않게 (INCIDENT-261027)
sudo chmod -x /etc/NetworkManager/dispatcher.d/90-onvif-restart

# 2) 모터 토크 해제 — onvif 가 멈춰야 포트가 열린다 (mk3-basic 은 포트 독점)
sudo python3 -c "
import serial, time
for p in ('/dev/ttyAMA0', '/dev/ttyAMA2'):
    s = serial.Serial(p, 115200, timeout=1); s.write(b'R\n'); s.flush()
    time.sleep(1.2); s.close(); print(p, 'disarmed')"
```

### 재가동

긴급 정지한 onvif_srvd 는 네트워크를 다시 연결해도 **자동으로 살아나지 않는다.** 점검이 끝나면 직접 켠다.
모터가 꺼진 상태이므로 onvif 가 상태를 보고 **현재 자세 그대로** `S` 만 보낸다(고개를 들어 올리지 않음).

```bash
sudo chmod +x /etc/NetworkManager/dispatcher.d/90-onvif-restart
sudo systemctl enable --now onvif_srvd.service
sudo journalctl -u onvif_srvd -b | grep PTZ-CMD | tail -2     # S - not armed, hold <각도>
```

## 배포 후 체크리스트

- [ ] `systemctl is-active` = active, `--version` 의 MK3 build 가 기대한 값
- [ ] 로그에 `PTZ-ALERT` 없음, 재시작이면 `PTZ-CMD ... none` (명령 0건)
- [ ] `onvif_srvd --mcu-info` 두 축 `normal`, 펌웨어 버전 기록
- [ ] `onvif_cam_view.py` 두 화면 OK
- [ ] `onvif_pan_tilt.py --quick` PASS
- [ ] 백업 파일(`onvif_backup_<날짜>/`) 존재
- [ ] (선택) 콜드부팅 1회: 30초에 `S`, 처진 자세 그대로, 떨림 없음
