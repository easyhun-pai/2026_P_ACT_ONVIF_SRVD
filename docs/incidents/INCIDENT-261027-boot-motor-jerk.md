# ptz018 부팅 시 모터 떨림 — onvif_srvd 반복 재시작으로 R/S 중복 전송

작성일: 2026-10-27 · 대상: ptz018 (<ptz018-ip>, MK3-xxxxxxxx) · 상태: **조치 완료**

## 1. 현상

- 전원 인가/부팅 직후 PTZ 모터가 약 7초간 "부르르" 떨림.
- `systemctl disable onvif_srvd` 후 약 2초로 줄었으나 사라지지 않음.
- 부팅 후 정상 동작 중에는 이상 없음.

## 2. 원인

부팅 중 **onvif_srvd가 4~5회 연속 재시작**되면서, 매 기동마다 모터 MCU에 `R`→`S` 초기화가 반복 전송됨.

- onvif_srvd(`SerialInit`)는 기동할 때마다 `/dev/ttyAMA0`(pan), `/dev/ttyAMA2`(tilt)에
  `R`(리셋·센서 재정렬·토크 해제, 2~3초 소요) → 1초 → `S`(arm, MCU 재초기화)를 보낸다. ([HARDWARE.md](../HARDWARE.md))
- NetworkManager dispatcher `/etc/NetworkManager/dispatcher.d/90-onvif-restart`가
  `lo up`, `eth1 up`, `eth0 up`, `eth0 dhcp4-change` 이벤트마다 **IP 변화와 무관하게** `systemctl restart onvif_srvd wsdd` 실행.
  이벤트가 직렬 처리되어(sleep 1 + wsdd 정지 ~2초) 약 3초 간격으로 재시작.
- 여기에 systemd 자체 기동(2.76초)까지 더해져 첫 인스턴스는 `R`만 보내고 1.1초 만에 종료됨.
- 결과적으로 **정렬(2~3초)이 끝나기 전에 다음 R이 계속 들어가** 모터가 떨림.

수정 전 콜드 부팅 타임라인(monotonic):

| 시각 | 기동 계기 | 모터 명령 |
|---|---|---|
| 2.76s | systemd (enabled) | `R`만 (1.1초 후 종료, `S` 미전송) |
| 3.91s | dispatcher `lo up` | R→S |
| 7.10s | dispatcher `eth1 up` | R→S |
| 10.16s | dispatcher `eth0 dhcp4-change` | R→S |
| 13.23s | dispatcher `eth0 up` | R→S |

`disable`이 효과가 작았던 이유: 2.76s 기동 1회만 빠질 뿐, dispatcher가 `restart`로 계속 띄움.

### 검증

| 테스트 | 결과 |
|---|---|
| 정상 동작 중 `systemctl restart onvif_srvd` (드라이버 이미 정렬됨) | 떨림 없음 |
| 콜드 부팅, onvif 기동 완전 차단(R/S 0회) | **움직임 전혀 없음** → 하드웨어/전원 인가 원인 배제 |
| 콜드 부팅, 기존 설정(R/S 4~5회) | 3회가량 들썩 |
| 정상 유닛 ptz020 비교 | onvif_srvd 바이너리 동일(md5 `448443cd`), 부팅 중 재시작 5~6회로 **동일 구조** → 전 장비 공통 잠재 이슈 |

## 3. 대응

부팅 중 onvif_srvd가 **1회만** 기동되도록 수정 (기능 유지).

| 파일 | 변경 |
|---|---|
| `/etc/NetworkManager/dispatcher.d/90-onvif-restart` ([deploy/90-onvif-restart](../../deploy/90-onvif-restart)) | `lo` 무시, ONVIF가 쓰는 IP가 **실제로 바뀐 경우에만** `try-restart` |
| `/home/ptz/edge/onvif_start.sh` ([deploy/onvif_start.sh](../../deploy/onvif_start.sh)) | 사용 IP를 `/run/onvif_srvd.ip`에 기록, `--detect` 옵션 추가 |
| `onvif_srvd.service` | `Wants/After=network-online.target` — 127.0.0.1로 먼저 떴다가 재시작되는 것 방지 (ptz018은 drop-in `/etc/systemd/system/onvif_srvd.service.d/10-wait-network.conf`로 적용) |
| `onvif_srvd` | 임시로 disable 해둔 것을 enable로 원복 |
| [DEPLOY.md](../DEPLOY.md) 긴급정지 절차 | disable만으로는 dispatcher가 다시 띄운다는 점과 차단 방법 추가 |

ptz018 백업: `/home/ptz/edge/_backup_vibfix_20261027/`

원복:

```bash
B=/home/ptz/edge/_backup_vibfix_20261027
sudo cp -a $B/90-onvif-restart /etc/NetworkManager/dispatcher.d/
sudo cp -a $B/onvif_start.sh /home/ptz/edge/
sudo rm -r /etc/systemd/system/onvif_srvd.service.d && sudo systemctl daemon-reload
```

## 4. 결과

수정 후 부팅 로그:

```
[6.07] Started onvif_srvd.service            ← 1회, IP=<ptz018-ip>
[6.26] nm-onvif: [up] eth1 — IP 동일(<ptz018-ip>), 재시작 생략
[7.29] nm-onvif: [dhcp4-change] eth0 — IP 동일(<ptz018-ip>), 재시작 생략
[8.31] nm-onvif: [up] eth0 — IP 동일(<ptz018-ip>), 재시작 생략
```

- 여러 차례 재부팅/콜드 부팅: **들썩임 1회(정상 초기화 동작), 떨림 없음.**
- onvif_srvd / wsdd / edge-ptz active, 시리얼 점유 정상, PTZ API 응답 정상.

## 5. 후속

- 같은 구조이므로 **전 장비에 동일 적용 권장** (ptz020 등).
  - 장비마다 `onvif_start.sh` 버전이 다르다(ptz020은 MQTT 모드 분기 포함). 파일을 통째로 덮어쓰지 말고
    `--detect` 블록과 IP 기록 줄만 끼워 넣을 것.
  - dispatcher는 유닛 ExecStart에서 기동 스크립트 경로를 읽고, `--detect` 미지원이면 재시작하지 않는다
    (구버전 스크립트를 `--detect`로 부르면 onvif_srvd가 하나 더 떠서 시리얼 이중 점유).
- ptz018은 edge 코드가 구버전(updater.py, selfcheck.py 등 없음) — 이번 이슈와 무관하나 버전 정렬 필요.
- ptz018 저장 위치 tilt 0.112 rad(6.4°)로 엔코더 0 경계 근처. 정렬 시 회전수 브랜치 이슈 가능성([HARDWARE.md](../HARDWARE.md)) 있으니 모니터링.
- 미확인: IP 변경 시 재시작 경로(테스트 시 모터 R/S 발생)는 코드 리뷰로만 확인, 실제 IP 변경 테스트는 안 함.
