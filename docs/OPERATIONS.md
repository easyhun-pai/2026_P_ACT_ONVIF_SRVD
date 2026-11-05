# 운용 (mk3-basic)

## 상태 · 설정 파일

`/var/lib/onvif_srvd/` (재부팅해도 유지)

| 파일 | 내용 | 비고 |
|---|---|---|
| `position.txt` | 마지막 위치 `pan tilt zoom` (라디안) | 기록용. 시작 시 위치는 MCU 목표각으로 맞춘다 |
| `mcu_offset` | 축별 센서 offset (`pan 5.68` / `tilt 3.35`) | 기동 중 읽은 값. 콜드부팅 때 처진 자세 각도 계산에 사용. 지우면 다음 기동 때 다시 기록 |
| `mount_mode` | `stand` / `hang` | `hang` 이면 tilt 부호 반전. 없으면 `stand` |
| `presets.txt` | ONVIF 프리셋 | 한 줄 `token pan tilt zoom 이름` (이름은 줄 끝까지, 띄어쓰기·한글 가능). 줌은 저장 순간 줌카메라에서 읽은 실제 값 |
| `home.txt` | 홈 위치 `pan tilt zoom` | SetHomePosition 때 기록, 시작 시 읽음 |
| `ptz_watch.conf` | 이동 감시 설정 (`key = value`, 없으면 기본값) | [PTZ_STREAMING.md](PTZ_STREAMING.md) |
| `device_id` | 장치 식별자 (MQTT 토픽, ONVIF 계정 확인 기준) | 없으면 밖에서 오는 ONVIF 는 모두 거부 |
| `onvif_auth` | 웹 비밀번호 원문 (root 600) | edge 가 비밀번호 변경 때 씀. ODM·NVR Digest 확인용 ([WSSE.md](WSSE.md)) |
| `onvif_auth_off` | 있으면 ONVIF 계정 확인 끔 (비상용) | `sudo touch` 후 바로 적용, 지우면 다시 확인 |
| `tracking_lock` | 있으면 ONVIF 이동 명령 무시 | 추적 기능이 잡고 있을 때 |

`/run/onvif_srvd/` (재부팅하면 사라짐)

| 파일 | 내용 |
|---|---|
| `live` | 실시간 각도 — 0.5초마다 MCU 에 `T` 조회 (pan/tilt 현재·목표·offset·상태) |
| `mcu_info` | 시작 때 기록 — 펌웨어 버전, 기동 상태, 보낸 조치, 펌웨어 한계, `I` 출력 |
| `started` | 이번 부팅에 onvif 가 한 번 시작했다는 표식 (콜드부팅 첫 시작 판별용) |

## 자주 쓰는 명령

```bash
# 모터 상태
onvif_srvd --mcu-info            # 실시간 각도 + 시작 기록 요약
onvif_srvd --mcu-info=full       # + 펌웨어 설정(I)
onvif_srvd --mcu-watch           # 1초마다 다시 표시, Ctrl+C 종료 (--mcu-watch=2 → 2초)
onvif_srvd --version             # SW 버전

# 로그
sudo journalctl -u onvif_srvd -b | grep PTZ           # 이번 부팅
sudo journalctl -u onvif_srvd -b -1 | grep PTZ        # 직전 부팅
sudo journalctl -u onvif_srvd -f | grep PTZ           # 실시간

# 재시작 / 자동시작
sudo systemctl restart onvif_srvd     # 모터가 켜져 있으면 모터 명령 0건
sudo systemctl disable onvif_srvd
sudo systemctl enable  onvif_srvd

# 시리얼 포트를 누가 쥐고 있나
sudo fuser -v /dev/ttyAMA0 /dev/ttyAMA2
```

| 로그 머리 | 뜻 |
|---|---|
| `PTZ:` | 시작 판정(펌웨어, 기동 여부, 콜드부팅 여부), 위치 동기화 |
| `PTZ-CMD:` | 모터에 보낸 명령과 이유 (`none` = 보내지 않음) |
| `PTZ-MCU:` | 우리 `S` 직후 모터 보드 메시지 (`MOT: Init`, `Motor ready` 등) |
| `PTZ-MON:` | 기동 후 30초, 1초마다 목표/현재 각도 |
| `PTZ-ALERT:` | 이상 — 보드 자체 재부팅, 우리 `S` 없이 나온 보드 메시지, 모터 꺼짐, 목표 미유지, 무응답, 줌카메라 조회 실패·계정 없음. **자동 재시도 없음** |
| `PTZ: arrived ...` / `PTZ-ALERT: NOT_REACHED·DRIFT·CORRECTION_FAILED` | 이동 감시 결과 ([PTZ_STREAMING.md](PTZ_STREAMING.md)), 바뀔 때만 |
| `ONVIF-AUTH: allowed <요청> from <IP> (digest/text)` | 밖에서 계정 확인 통과 (같은 IP·결과는 30초에 한 번) ([WSSE.md](WSSE.md)) |
| `ONVIF-AUTH: DENIED <요청> from <IP> (<이유>)` | `no-credentials` 계정 없음 · `wrong-password` · `wrong-user` · `locked-now`/`locked` 5번 틀려 60초 잠김 · `digest-needs-password-file` 원문 파일 없음(웹 비밀번호 다시 저장) · `no-device-id` |
| `PTZ: zoom camera ...` | 줌카메라 주소·계정 출처(`account from ...`), 조회 `OK` / `OK again` (실패는 `PTZ-ALERT`, 끊길 때 한 번) |

## 장비 시험 도구 (`/home/ptz/workspace/onvif_setup`)

PC 에서 SSH 로 장비에 접속해 실행한다. PC 는 SSH 와 브라우저만 있으면 된다 (운영체제 무관).

```bash
python3 ~/workspace/onvif_setup/onvif_cam_view.py          # PC 브라우저 http://<장비IP>:8090 (광각/줌 + OK)
python3 ~/workspace/onvif_setup/onvif_pan_tilt.py --quick  # 팬/틸트 시험 약 25초 (전체는 옵션 없이 약 2분)
python3 ~/workspace/onvif_setup/onvif_pan_tilt.py --quick --video
python3 ~/workspace/onvif_setup/onvif_move.py 0 90        # 팬 0°, 틸트 90°로 이동 (기본 단위 도, --rad, --preset N, --list)
sudo python3 ~/workspace/onvif_setup/onvif_zoom_test.py   # 줌 위치 시험 — 줌 3배/1배로 움직이고 시험 프리셋 ztest 를 만들었다 지움, 끝나면 줌 복귀
```

`onvif_pan_tilt.py`, `onvif_move.py` 는 ONVIF 로 움직이므로 onvif 를 멈출 필요가 없다.
`onvif_pan_tilt.py` 결과는 `logs/onvif_pan_tilt_<날짜_시각>.csv` (지점별 각도·오차·시간·결과, 1KB 미만), 7일 지난 것은 다음 시험 때 자동 삭제.

## ★ 시리얼 포트는 한 프로세스만 쥔다

mk3-basic 은 `/dev/ttyAMA0`, `/dev/ttyAMA2` 를 **독점**한다(`flock` + `TIOCEXCL`). 다른 프로그램은 열 수 없다.
과거 두 프로그램이 같은 포트로 `R`/`S`/`T` 를 보내 모터가 휘청거린 사례가 있다
([incidents/ISSUE-205-api-ptz-wobble.md](incidents/ISSUE-205-api-ptz-wobble.md)).

**원칙: 한 모터에 컨트롤러는 하나.** 다른 앱이 PTZ 를 써야 하면 시리얼을 직접 열지 말고
**ONVIF 클라이언트로** `127.0.0.1:1000` 에 AbsoluteMove 를 보낼 것 (edge-ptz API 가 이 방식).

`tools/` 의 직접 제어 스크립트(`pantilt.py`, `ptz_key.py`, `ptz_cont.py`, `ptz_move.py`)는 시리얼을 직접 연다.
**쓰기 전에 onvif 를 멈춰야 한다** (멈추지 않으면 `Device or resource busy`). `pantilt.py` 는 시작할 때 R→S 로 고개를 0,0 으로 들고,
끝날 때 R 로 모터를 끈다 — 끝난 뒤 onvif 를 켜면 꺼진 축만 현재 자세로 다시 기동한다.

```bash
sudo systemctl stop onvif_srvd
sudo python3 tools/ptz_key.py
sudo systemctl start onvif_srvd
```

## ONVIF 엔드포인트

| 항목 | 값 |
|---|---|
| 포트 | `1000` |
| device | `http://<IP>:1000/onvif/device_service` |
| media | `http://<IP>:1000/onvif/media_service` |
| ptz | `http://<IP>:1000/onvif/ptz_service` |
| 프로필 토큰 | 현장 edge 설정은 `MainStream` (GetProfiles 로 확인) |

AbsoluteMove 의 `PanTilt x/y` 는 **라디안 직접 값**이다 (정규화 좌표 -1~1 이 아님).
선택 항목 `Speed.PanTilt.x` (0~1): 없으면 기본 속도(팬 1.6 rad/s), 1.0 = 팬 3.0 rad/s (펌웨어 최대).

## 자동 탐색(WS-Discovery)

ODM 등 탐색 기반 도구에 장치가 안 뜨면 `wsdd` 데몬 유무를 확인한다.

```bash
systemctl status wsdd
```

WS-Discovery 는 멀티캐스트라 **ZeroTier/서브넷을 넘지 못한다.** 원격 관리 도구에는 IP 로 직접 등록한다.
