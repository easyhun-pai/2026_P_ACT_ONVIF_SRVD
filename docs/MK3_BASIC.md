# onvif_srvd mk3-basic — 설계와 검증 (2026-11)

현장 원본 바이너리(md5 `448443cd`)를 upstream 기준으로 다시 작성하고, **부팅 때 모터를 다루는 방식**을 바꾼 빌드.
목적은 SW 동작을 예측 가능하게 만들고, 부팅 떨림(ptz018, [incidents/ISSUE-TRACKER-ptz018.md](incidents/ISSUE-TRACKER-ptz018.md))을
일으키던 동작을 피하는 것.

| 항목 | 값 |
|---|---|
| 기반 | upstream `KoynovStas/onvif_srvd` `df09d0a` (v2.0-29) |
| 변경 파일 | `src/ServicePTZ.cpp`, `src/onvif_srvd.cpp`, `src/CMakeLists.txt` (`src/mk3-basic.patch` 한 장으로도 적용) |
| gsoap | 시스템 2.8.124 (`-DUSE_SYSTEM_GSOAP=1`) |
| 검증 장비 | ptz018 (Raspberry Pi CM5, Debian 12, PAN v2.3.0-manual / TILT v1.0.6) |
| 검증 빌드 md5 | `2a450e4c1429904c67a9a242261636a8` (`mk3-basic 2026-11-03g`), 줌 수정 `a6856dac39b085ec5d1d8da20d1d6a19` (`mk3-basic 2026-11-04 zoomfix`) |

## 원본과 같은 것

현장 원본 바이너리의 심볼·문자열로 기능 범위를 확인하고 그대로 맞췄다.

- Pan/Tilt 시리얼 제어 (`/dev/ttyAMA0`, `/dev/ttyAMA2`, `T<rad>`), 연속 이동 스레드(20ms), 5초 무명령 자동 정지
- 절대/상대 이동, 프리셋(`/var/lib/onvif_srvd/presets.txt`), 홈 위치, 위치 저장(`position.txt`)
- 줌 카메라(192.168.1.68) ONVIF SOAP 호출
- MQTT 자세 발행(`telemetry/<device_id>/ptz`, 원본과 같은 JSON), 거치 모드(hang), tracking lock

v8 guard(스톨 가드, 래치, 잠금, 한계 학습, 부팅 자동 복원, 자동 재기동)는 넣지 않았다. v8 은 저장소 기록에 남아 있다.

## 바뀐 것

| # | 내용 | 이유 |
|---|---|---|
| 1 | **부팅·재시작 때 R 을 보내지 않고, 이동 명령도 보내지 않음.** 기동돼 있으면 명령 0건 | 불필요한 MCU 리셋·이동 제거 |
| 2 | **콜드부팅: 부팅 30초 후 기동** (`PTZ_ARM_DELAY_S`, 기본 30) | 전원·PoE 가 안정된 뒤 모터를 켬 |
| 3 | **기동 시 현재(처진) 자세 그대로 힘만 넣음** — `S` 직후 3초간 현재 자세를 20ms 마다 목표로 보냄 | 떨림을 일으키던 '고개를 0,0 으로 들어 올리기' 제거 |
| 4 | 기동 전에 들어온 절대/프리셋/홈/상대 이동은 기억했다가 기동 후 실행. 연속 이동은 무시(로그) | 앱 요청 유실 방지 |
| 5 | **자동 재시도 없음.** 모터 보드가 혼자 리셋되거나 힘이 빠지면 `PTZ-ALERT` 로그만 | 전원 문제일 때 꺼짐/켜짐 반복 방지 |
| 6 | 로그: `PTZ-CMD`(보낸 명령과 이유), `PTZ-MCU`(기동 중 보드 메시지), `PTZ-MON`(기동 후 30초, 1초 단위), `PTZ-ALERT`(이상) | 장애 시 증거 |
| 7 | `onvif_srvd --mcu-info[=full]`, `--mcu-watch[=초]`: 실시간 각도 + 펌웨어 버전·기동 상태 | 버전 관리, 현장 확인 |
| 8 | 시리얼 포트 독점 (`flock` + `TIOCEXCL`) + 전용 수신 스레드 | 다른 프로그램의 동시 접근 사고 방지 (ISSUE-205) |
| 9 | 시작 시 ONVIF 위치를 MCU 목표각으로 동기화 | position.txt 와 실제 위치 불일치 해소 |
| 10 | 한계 = 스펙 ∩ 펌웨어 한계(`I` 의 Min/Max Angle) | |
| 11 | 단발 이동은 작은 `T` 를 연속 전송(램프). AbsoluteMove `Speed`(0~1) 지원 | 큰 단발 `T` 는 구동 안 됨 ([HARDWARE.md](HARDWARE.md) 3절) |
| 12 | `onvif_start.sh` IP 자동 선택에서 eth1/br-sensor 제외 | DHCP 실패 시 내부망 IP 로 뜨던 문제 |
| 13 | 장비가 출력하는 문구는 모두 ASCII | PC 운영체제·터미널 종류와 무관 |
| 14 | **줌 위치를 줌카메라에서 읽음** (2026-11-04) — 0.5초마다 백그라운드로 줌카메라 GetStatus(`Position/Zoom@x`). SetPreset·SetHomePosition·RelativeMove(줌)는 그 자리에서 한 번 더 읽음(1초 제한, 무응답 중이면 마지막 값) | 웹·edge·NVR 이 줌카메라를 직접 움직이면 onvif 의 줌이 0 에 머물러 프리셋이 1배로 저장되던 문제. ONVIF 요청은 한 스레드에서 처리되므로 요청 안에서 줌카메라를 기다리지 않게 함 |
| 15 | 홈 위치를 `/var/lib/onvif_srvd/home.txt` 에 저장 | 재시작하면 홈이 사라지던 문제 |
| 16 | 줌카메라 계정: env `ZOOM_CAM_USER`/`ZOOM_CAM_PASS` > `mediamtx.yml` `detection_zoom` 주소 (edge `zoom_camera.credentials()` 와 같은 순서). 소스에서 계정 삭제, 못 찾으면 줌 제어 끔 + `PTZ-ALERT` | 장비마다 계정이 다를 수 있음, 소스에 비밀번호 노출 |

## 시작 흐름

```
ptz_init
 ├ 콜드부팅 판별: /run/onvif_srvd/started 없음 + rsts 0x20 비트 없음 → 콜드부팅 첫 시작
 ├ 축마다 V → T(상태 판정) → I(설정)        ※ v2.3.0 은 I 가 offset 을 채우므로 반드시 T 다음
 ├ 기동돼 있음(offset≠0, |현재−목표|<0.15) 이고 콜드부팅 아님 → 명령 없음, 이동 허용
 └ 그 외 → 유지할 각도 계산
            offset≠0 이면 wrap(보고된 현재각), 아니면 wrap(원시각 − 저장된 offset)
            (/var/lib/onvif_srvd/mcu_offset, 없으면 v2.3.0 의 I Sensor Offset)
          → 백그라운드 기동: (콜드부팅이면 uptime 30초까지 대기) → 두 축 S 동시
            → 3초간 유지 각도 스트림 → 상태 확인 → 위치 동기화 → 이동 허용 → 대기 중 이동 실행
            → 30초 상태 기록(PTZ-MON) → 0.5초마다 상태 조회(/run/onvif_srvd/live), 이상 시 PTZ-ALERT
```

유지 각도를 계산할 수 없으면(첫 설치 + v1.0.6) 유지 없이 `S` → MCU 기본 목표 0,0 으로 간다 (`PTZ-CMD ... no hold -> MCU goes to 0`).

## 실측 근거 (2026-11-02~03, 비교 장비 / ptz018)

| 사실 | 확인 |
|---|---|
| 펌웨어는 전원 인가 후 스스로 기동하지 않음 | 비교 장비, ptz018 |
| 값 없는 `T` = 상태 조회 (v2.3.0, v1.0.6 모두). 미기동이면 offset 0.00, 현재각은 원시값 | 두 장비 |
| Pi 재부팅 시 MCU 는 기동 상태·목표각 유지 | 두 장비 |
| 기동 중 `S` 를 다시 받아도 목표 유지 (짧은 재초기화 움찔) | v2.3.0, v1.0.6 |
| v2.3.0 은 `I` 를 받으면 미기동이어도 offset 을 채움. 콜드부팅 직후 pan offset 이 채워진 채 보인 경우도 있음 | ptz018 pan |
| Pi 리셋 원인 `rsts`: 콜드부팅 `0x1000`, `sudo reboot` `0x1020` | ptz018 |
| **미기동 MCU 는 `S` 전에 받은 `T` 를 무시** | ptz018 |
| **`S` 직후부터 현재 자세를 연속 전송하면 그 자리에서 기동 (이동 없음)** | ptz018 |
| 각도 = wrap(원시각 − offset). `Current angle` 은 바퀴 수가 누적될 수 있음(−4.40 = +1.88 − 2π) | 비교 장비 tilt, ptz018 pan |
| 틸트 0° = 렌즈가 위(돔 꼭대기), 90° = 수평 정면 | ptz018 사진 |

## 시험 결과 (ptz018)

| 시험 | 결과 |
|---|---|
| onvif 재시작 / `sudo reboot` (기동 상태) | 모터 명령 0건, 자세 그대로 |
| R 로 끈 뒤 시작 (미기동) | 꺼진 축만 `S` + 현재 자세 유지 |
| 콜드부팅 7회 (거꾸로 매단 자세 1회 포함) | uptime 30초에 `S`, 처진 자세 그대로, **떨림·움직임 없음** |
| 콜드부팅 (이전 방식: 기동 즉시 + 0,0 이동) | 떨림 3~7초 (롤 방향) |
| 기동 전 이동 요청 (15초에 AbsoluteMove) | 30초 기동 후 33초에 실행, 정상 도달 |
| 실행 중 tilt 에 R (모터 꺼짐) | 0.03초 뒤 `PTZ-ALERT`, 1초 뒤 감시 `motor is OFF`, 재시도 없음 |
| 절대/연속 이동, 프리셋 | 정상 |
| `tools/onvif_setup/onvif_pan_tilt.py --quick` | 6지점 OK, 24초, `PTZ-ALERT` 0 |
| 부팅 9~14초 "딱딱" 소리 | onvif 를 끈 채 콜드부팅해도 남 → 하드웨어 자체 소리 (SW 무관) |

## 개발 중 발견한 버그와 수정

| 증상 | 원인 | 수정 |
|---|---|---|
| 포트 연 직후 첫 조회 무응답 | 첫 명령 유실 | 무응답 시 1회 재시도 |
| 틸트가 기동 중인데 미기동 판정 | 틸트가 자중으로 ~0.07 rad 처진 채 유지 | 허용 오차 0.05 → 0.15 rad |
| R 직후인데 pan 을 기동으로 오판 | `I` 가 offset 을 채움 | 판정(T)을 `I` 보다 먼저 |
| 콜드부팅 직후 pan offset 이 채워져 있음 | 펌웨어 동작 (원인 미상) | 리셋 원인 레지스터로 콜드부팅 판별 |
| pan 만 먼저 돌면서 떨림 | 축별 순차 기동 | `S` 동시 전송 |
| 기동 시 고개를 들어 올리며 떨림 | MCU 가 `S` 후 0,0 으로 이동 | `S` 직후 현재 자세 연속 전송 |
| 콜드부팅 후 첫 onvif 재시작에 `S` 재전송 | `/run/onvif_srvd/` 폴더가 없어 시작 표식 미기록 | 표식 전에 폴더 생성, 실패 시 `PTZ-ALERT` |
| 콜드부팅 때 팬이 0° 까지 108° 회전 | 바퀴 누적 각도를 그대로 범위 비교 → 유지 실패 | 각도를 [−π, π] 로 접음 |

## 줌 위치 시험 (ptz018, 2026-11-04, 빌드 md5 `a6856dac`)

| 시험 | 결과 |
|---|---|
| 웹 줌 3배 → ONVIF GetStatus | 0.221 |
| ONVIF SetPreset → presets.txt | 0.221 |
| 웹 1배 → ONVIF GotoPreset → 줌카메라 | 0.220 (복귀) |
| 연속 줌 뒤 RelativeMove +0.1 | 0.653 → 0.702 (튐 없음) |
| SetHomePosition → 재시작 | home.txt 에서 다시 읽음 |
| GetStatus 응답 | 약 0.4 ms |
| 줌카메라 차단(약 10초) | GetStatus 3 ms, SetPreset 1 ms, `PTZ-ALERT` 1회 → 회복 로그 |
| 계정 없음(mediamtx.yml 없음) | 줌 제어 꺼짐 + `PTZ-ALERT`, 모터 쪽은 정상 시작 |
| 설치 시 모터 | 명령 0건 |

줌카메라(UV-ZNH4110M)는 Digest 전용 curl 요청(빈 본문 탐색 POST)에 인증 요구 없이 200 을 돌려줘서 본 요청이 401 이 된다.
인증 방식 자동(`CURLAUTH_ANY`) + 요청마다 새 핸들로 처리한다 — 핸들을 재사용하지 말 것.

## 주의

- **edge 업데이트(`install.sh`)가 바이너리와 `onvif_start.sh` 를 덮어쓴다.** 정식 반영은 edge 패키지에 넣어야 한다.
- 콜드부팅 후 고개는 **전원이 꺼질 때 처진 자세**(실측 틸트 1.15~1.34 rad ≈ 66~77°)로 유지된다. 정해진 자세로 보내는 건 앱/운영자 몫.
- onvif 실행 중에는 다른 프로그램이 모터 시리얼을 열 수 없다(독점). `tools/pantilt.py` 등 직접 제어 도구는 onvif 를 멈춘 뒤 쓴다.
  onvif 를 켠 채 시험하려면 `tools/onvif_setup/onvif_pan_tilt.py` 를 쓴다.
- 진단 로거(`motor-log.service` 등)를 같이 띄우지 말 것 — 포트를 독점·직접 읽는다.
- 구버전 TILT 펌웨어(v1.0.6)의 떨림 원인 자체는 그대로다. 이 빌드는 그 문제를 일으키는 동작을 피할 뿐이다.
