# 2026_P_ACT_ONVIF_SRVD

P-ACT(MK3) PTZ 카메라의 ONVIF 서버 `onvif_srvd` 개조본 — ONVIF PTZ 명령을 팬/틸트 모터 보드(STM32 FOC) 명령으로 전달하고,
부팅 때 모터 상태를 보고 판단해 불필요한 리셋·이동을 하지 않는다 (**mk3-basic**).

- 작업 정리: [CONTRIBUTIONS.md](CONTRIBUTIONS.md)
- 종류: 재사용 도구
- 담당: 이지훈 주임
- 기반: 사내 저장소 `2026_ONVIF_SRVD`(비공개) (`branch_261027` 기록을 이어받음),
  upstream [KoynovStas/onvif_srvd](https://github.com/KoynovStas/onvif_srvd) @ `df09d0a` (v2.0-29)

## 버전

| 버전 | 날짜 | 바이너리 md5 | 내용 |
|---|---|---|---|
| **v1.0** | 2026-11-05 | `e4d4621a` | mk3-basic + 줌 위치 + 이동 감시(스트리밍 모드) + v2.4+ 펌웨어 기동 판정 + **ONVIF 계정 확인** (admin + 웹 비밀번호, edge 패치 같이 — [WSSE.md](docs/WSSE.md)) |

SW 버전 확인 (장비에서): `md5sum $(which onvif_srvd) | cut -c1-8` · 빌드 이름: `onvif_srvd --version`
이전 빌드·정리한 브랜치 기록: [docs/VERSIONS.md](docs/VERSIONS.md)

## 무엇이 다른가

| | 현장 원본 (448443) | v8 guard (이전 개조) | **mk3-basic (현재)** |
|---|---|---|---|
| 부팅 때 | R→S, 모터가 0,0 으로 이동 | 위치 복원 이동 | **상태 판정** — 켜져 있으면 명령 0건, 꺼져 있으면 현재 자세 그대로 S |
| 콜드부팅 | 즉시 | 즉시 | 30초 뒤, 고개를 들어 올리지 않음 |
| 모터 꺼짐 | 모름 | 자동 재무장 | `PTZ-ALERT` 로그만, 자동 재시도 없음 |
| 시리얼 | 쓰기만 | 쓰기+읽기 | 독점 + 수신 스레드, 0.5초 상태 조회 |
| 확인 명령 | - | - | `onvif_srvd --mcu-info` / `--mcu-watch` |
| 줌 위치 | 항상 0 (자기가 보낸 값만 앎) | 같음 | **줌카메라에서 실제 줌을 읽음** — 프리셋·GetStatus 정확 (11-04) |
| 줌카메라 계정 | 소스 상수 | 같음 | `mediamtx.yml` 에서 읽음 (소스에 없음) |
| 이동 후 | 명령만 보내고 끝 | 스톨 가드 | **이동 감시(스트리밍 모드)** — 목표 기억, 도착 확인(`NOT_REACHED`), 틀어짐(`DRIFT`), 보정은 기본 꺼짐 (11-04) |
| GetStatus | 명령값, 항상 IDLE | 같음 | **실측 위치**, MOVING/IDLE, `Error` 사유 → edge 수정 없이 플랫폼 자세가 실측 |
| 모터 펌웨어 v2.4+ | - | - | `Q` 상태로 기동 판정 (라이다 신규 v2.5.1, 켜짐 비트는 실장비 확인 전) |
| ONVIF 계정 | 헤더가 붙으면 모든 요청 거부 (`MustUnderstand`), 없으면 누구나 | 같음 | **admin + 웹 비밀번호 확인** (Digest·Text) — ODM·NVR 계정 등록 → PTZ + 영상, 틀리면 PTZ 도 거부. 장비 안(127.0.0.1)은 그대로 (11-05) |

자세한 설계·실측 근거·시험 결과: [docs/MK3_BASIC.md](docs/MK3_BASIC.md) · 이동 감시: [docs/PTZ_STREAMING.md](docs/PTZ_STREAMING.md) · 계정 헤더: [docs/WSSE.md](docs/WSSE.md)

## 구성

| 경로 | 내용 |
|---|---|
| `src/ServicePTZ.cpp` | PTZ 서비스 + 모터 제어 (mk3-basic) |
| `src/onvif_srvd.cpp` | upstream main + `ptz_init()` 연결, `--mcu-info` / `--mcu-watch` / `--version` |
| `src/CMakeLists.txt` | upstream CMake + 빌드 정보(`MK3_BUILD_INFO`), curl/mosquitto 링크 |
| `src/mk3-basic.patch` | upstream `df09d0a` 에 `git apply` 하면 위 세 파일과 같아짐 |
| `deploy/` | `onvif_start.sh`(현장 edge 기준 + IP 선택 수정), systemd 유닛, NetworkManager dispatcher |
| `tools/onvif_setup/` | **장비 시험 도구** — 카메라 화면 확인(PC 브라우저), ONVIF 팬/틸트 시험, 한 줄 이동, 줌 위치·이동 감시·계정 헤더 시험 |
| `tools/make_package.py` | 배포 묶음(zip) 만들기 |
| `tools/pantilt.py` 외 | 시리얼 직접 제어 도구 (onvif 를 멈춘 뒤 사용) |
| `docs/` | [HARDWARE](docs/HARDWARE.md)(★ 코드 만지기 전 필독) · [PTZ_STREAMING](docs/PTZ_STREAMING.md) · [WSSE](docs/WSSE.md) · [VERSIONS](docs/VERSIONS.md) · [BUILD](docs/BUILD.md) · [DEPLOY](docs/DEPLOY.md) · [OPERATIONS](docs/OPERATIONS.md) · [HISTORY](docs/HISTORY.md) · [incidents/](docs/incidents/) |

## 실행·배포

빌드 (카메라 본체에서, [docs/BUILD.md](docs/BUILD.md)):

```bash
git clone https://github.com/KoynovStas/onvif_srvd.git && cd onvif_srvd && git checkout df09d0a
git apply /path/to/2026_P_ACT_ONVIF_SRVD/src/mk3-basic.patch
mkdir build && cd build
MK3_BUILD_INFO="mk3-basic $(date +%F)" cmake -DUSE_SYSTEM_GSOAP=1 .. && make -j4
```

배포 묶음 → 장비 설치 ([docs/DEPLOY.md](docs/DEPLOY.md)):

```bash
python3 tools/make_package.py --binary build/onvif_srvd     # dist/onvif_mk3_basic_<날짜>_<md5>.zip
scp dist/onvif_mk3_basic_*.zip ptz@<장비IP>:~/             # 이후 zip 안 device/INSTALL.txt 대로
```

설치 위치: `/usr/local/bin/onvif_srvd`, `/home/ptz/edge/onvif_start.sh`, 시험 도구 `/home/ptz/workspace/onvif_setup/`.
**edge 패키지 업데이트(`install.sh`)가 바이너리와 `onvif_start.sh` 를 덮어쓴다** — 정식 반영은 edge 패키지에.
**운영 카메라 배포는 매번 담당자 승인, 한 대씩.**

확인 (장비에서):

```bash
onvif_srvd --mcu-watch                                         # 펌웨어 버전, 실시간 각도, 상태
python3 ~/workspace/onvif_setup/onvif_cam_view.py              # PC 브라우저 http://<장비IP>:8090
python3 ~/workspace/onvif_setup/onvif_pan_tilt.py --quick      # 약 25초, VERDICT: PASS
python3 ~/workspace/onvif_setup/onvif_move.py 0 90              # 팬 0°, 틸트 90°(수평 정면)로 이동
sudo python3 ~/workspace/onvif_setup/onvif_zoom_test.py         # 줌 위치 시험 (줌이 잠깐 움직임), VERDICT: PASS
python3 ~/workspace/onvif_setup/onvif_stream_test.py move 0.5 1.2   # 이동 중/후 GetStatus (실측, MOVING/IDLE, Error)
python3 ~/workspace/onvif_setup/onvif_wsse_test.py              # 장비 안: 헤더 처리 시험, == ALL PASS
python3 onvif_auth_test.py <장비IP> --password <웹 비밀번호>      # PC 에서: 계정 확인 시험 (tools/onvif_setup), == ALL PASS
```

## 먼저 읽어야 할 것

코드를 고치기 전에 **[docs/HARDWARE.md](docs/HARDWARE.md)** 를 읽는다. 모르고 건드리면 모터가 폭주하거나 과열된다. 특히:

- **단발 큰 `T` 명령은 모터를 구동하지 못한다.** 작은 스텝의 연속 스트림만 움직인다.
- **`R` 은 MCU 재부팅 + 토크 해제**, `S` 는 재초기화 후 저장된 목표(전원 직후 0)로 이동한다.
- **각도는 바퀴 수가 누적돼 보고될 수 있다.** 비교·계산은 반드시 wrap 보정.
- **값 없는 `T` 로 기동 상태를 읽는다** (구 펌웨어 v2.3.0·v1.0.6 은 미기동이면 offset 0). `I` 는 미기동 MCU 의 offset 을 채우므로 판정 전에 보내지 않는다.
- **모터 펌웨어 v2.5.1(라이다 신규)은 꺼져 있어도 offset 을 보고한다** → `Q` 상태로 판정 ([PTZ_STREAMING.md](docs/PTZ_STREAMING.md)).
- **`systemctl stop` 으로는 모터 토크가 안 풀린다.** `R` 을 보내야 한다 ([DEPLOY.md](docs/DEPLOY.md) 긴급 정지).

## 데이터·모델 위치

해당 없음 (영상·데이터를 다루지 않음). 빌드 바이너리·배포 zip 은 저장소에 넣지 않는다 — 빌드로 만들거나 Release 에 첨부.
