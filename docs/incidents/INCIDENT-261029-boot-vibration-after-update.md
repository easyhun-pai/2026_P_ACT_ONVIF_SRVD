# ptz018 SW 업데이트 후 부팅 떨림 재발 — 조사 기록

작성일: 2026-10-29 · 대상: ptz018 (<ptz018-ip>, MK3-xxxxxxxx) · 상태: **원인 미확정, 조사 중 (PAN 축으로 좁혀짐)**
선행 건: [INCIDENT-261027-boot-motor-jerk.md](INCIDENT-261027-boot-motor-jerk.md)

## 1. 현상

- 10/27 수정 후에는 콜드 부팅·재부팅 모두 "들썩 1회, 떨림 없음"이 확인됐다.
- 10/29 edge SW 업데이트(v1.0.0-rc14) 후 콜드 부팅·`sudo reboot` 모두 **약 5초 이상 떨림** 재발.
- 일반 PoE → **PoE++로 바꾼 뒤 떨림 시간이 짧아짐**(현장 관찰). 사라지지는 않음.
- 장비는 PoE++ 필수 사양이며, 10/27 성공 당시를 포함해 **10/29 일반 PoE 테스트 외에는 항상 PoE++** 사용.
- **떨림 방향: 좌우(PAN 축).**

## 2. 현재 세팅 (2026-10-29 18:0x 기준)

전체 스냅샷: 장비 `/home/ptz/vibcheck_20261029/settings.txt`

| 항목 | 값 |
|---|---|
| edge SW | v1.0.0-rc14, commit 8d8bc32, built 2026-10-29 15:51 (`install.sh` v1.0.0-rc6 경로로 설치 이력 있음) |
| onvif_srvd | md5 `448443cd` (10/27과 동일, 바이너리 변경 없음) |
| onvif_srvd.service | enabled. 유닛 본체에 `Wants/After=network-online.target` 포함(업데이트로 반영됨) + drop-in `10-wait-network.conf` 유지 |
| 90-onvif-restart | md5 `b3402ad2` — 10/27 수정본과 동일 (edge `nm-onvif-restart`도 동일) |
| onvif_start.sh | 신버전(MQTT 모드 분기) + `--detect`/IP 기록 포함 |
| 부팅 콘솔 | 10/27 21:06에 변경됨: `console=tty3 quiet loglevel=0 ...`, serial-getty 마스크, `disable_splash=1` (ptz020과 같은 구성) |
| ptz_api | 기본 바인드 `127.0.0.1:7777` (외부 접속 불가, 의도된 변경) |
| 모터 MCU 펌웨어 | **PAN `v2.3.0-manual` / TILT `v1.0.6` — 축별로 다름** |
| PAN MCU 설정 | Motor Type PAN, min/max ±2.36, offset 5.68, dir CW, zero elec 3.36, vel PID 6/5/0, Tf 0.01, angle P 20, vel limit 3.0, **voltage limit 8.0**, align V 3.0, EEPROM 저장값 없음(기본값 사용) |
| TILT MCU 설정 | v1.0.6은 `I`/`E`/`A` 명령 미지원 → 확인 불가 |
| position.txt | `0.208 1.1388 0` (ONVIF 추정 pan 11.9°, tilt 65.2°) |

## 3. 확인한 것

### 3.1 Pi 쪽 부팅 명령은 10/27 수정 상태 그대로 정상

오늘 부팅 7회(-7 ~ 0) 모두:

- onvif_srvd 기동 **1회**, dispatcher 이벤트 3회 모두 "IP 동일, 재시작 생략" (또는 "미기동 상태, 생략")
- 부팅 중 PTZ API 이동 명령(`ContinuousMove/AbsoluteMove/Stop/GotoPreset`) **0건**
- 시리얼(`/dev/ttyAMA0`, `/dev/ttyAMA2`) 점유 프로세스는 onvif_srvd 하나뿐
- edge 코드(`*.py`, `*.sh`, tools)에서 시리얼을 여는 코드 없음, cron @reboot 없음

→ **모터로 나가는 부팅 명령은 R/S 1회뿐이며 10/27 성공 상태와 동일.** 업데이트가 부팅 명령 경로를 바꾸지는 않았다.

### 3.2 MCU 초기화 시퀀스 실측 (onvif 1회 재시작, 18:06:57)

onvif_srvd는 시리얼을 읽지 않으므로 별도 프로세스에서 **읽기 전용**으로 MCU 출력을 시간 기록.

| 재시작 후 | 이벤트 (PAN/TILT 동일) |
|---|---|
| 0.60s | `R` → 펌웨어 재부팅 배너 (`Firmware Version ...`, 타이머 초기화) |
| 1.62s | `S` → `MOT: Init` |
| 2.12s | `MOT: Enable driver.` (토크 인가) |
| 2.62s | `MOT: Align sensor.` → `Skip dir calib` / `Skip offset calib` → `Motor ready` |

- 에러·반복 리셋 없음. 정렬은 저장된 오프셋을 써서 즉시 끝남(보정 버즈 없음).
- → 떨림은 **토크가 들어간 뒤(Enable driver 이후) 목표 자세로 안착하는 과정**에서 나는 것으로 추정.

### 3.3 기타

- PAN 엔코더 노이즈(`A200`): p-p 0.003 rad, std 0.0005 — 센서 노이즈 문제 아님.
- PAN 센서각 5.68 ≈ 오프셋 5.68 → PAN은 MCU 기준 0 부근으로 추정. ONVIF는 pan 11.9°로 믿음
  → 10/27 후속 항목의 "R/S 후 위치 불일치"가 실측으로 확인됨(MCU 각도 = 센서각 − 오프셋은 추정).
- 10/29 `~/.bash_history`에 `workspace/edge-ptz-setup/pantilt.py` 실행 다수.
  이 스크립트는 onvif가 포트를 잡은 상태에서도 직접 R/S를 보내고, pan을 **±2.8 rad(±160°)** 로 스윕한다
  (PAN MCU 한계 ±2.36, 스펙 ±135° 초과). tilt도 0까지 내린다(엔코더 경계, HARDWARE.md 4절).
- PC에서 MCU 펌웨어를 새로 구운 흔적 없음(openocd 설치돼 있으나 관련 파일·로그 없음).

### 3.4 정정

- 처음에 TILT 수신 버퍼의 펌웨어 부팅 배너를 보고 "전원 부족(브라운아웃)으로 MCU 재부팅" 가설을 세웠으나,
  펌웨어 명령표상 `R` = "Reset system"(MCU 전체 재부팅)이라 **R에 대한 정상 반응**이었다. 브라운아웃 근거 아님.
- 10/27 문서에서 "정지 상태의 실제 각도를 읽는 방법 없음"이라 했으나, **PAN 펌웨어 v2.3.0에는 `A[n]`(센서각 샘플링),
  `I`(설정 조회)가 있어 읽을 수 있다.** TILT v1.0.6은 미지원.

## 4. 원인 가설 (미확정)

| 가설 | 근거 | 반론/미확인 |
|---|---|---|
| ~~A. 전원 여유 부족~~ (약화) | 일반 PoE에서 더 길었음 | 10/27 성공 때도 PoE++ → 전원은 원인 아님, 악화 요인일 뿐 |
| B. 안착 거리(시작 자세 ↔ MCU 목표) 차이 | 10/27 종료 자세(-21°, 6°)는 원점 근처, 오늘은 pantilt 스윕/조작 후 자세가 다양 | 물리 자세를 부팅마다 기록하지 않음 |
| C. pantilt.py 스윕으로 기구·배선 영향 | ±160° 스윕(한계 초과), tilt 0 도달 | 직접 증거 없음 |
| **D. PAN 보드 펌웨어/보정값** (유력) | 떨림이 PAN만. PAN만 커스텀 `v2.3.0-manual`, 부팅 시 저장된 Zero Electric Angle(3.36)로 `Skip offset calib`. 정지 중 PAN 구동 전압 -0.6~-0.9 V(중력 부하 없는 축인데 0이 아님) | 정상 유닛(ptz020) 비교 불가 — 현장 출고 |

### 3.5 11/02 재조회 (IP <ptz018-ip>로 변경됨, 가동 42분)

선임 제공 조회 스크립트(`I` 송신)로 확인. 10/29 값과 **전부 동일**:

```
[pan] v2.3.0-manual — Measured Yes, PAN, vel PID 6/5/0, Tf 0.01, angle P 20, vel limit 3, voltage limit 8, align V 3,
      offset 5.68, ±2.36, CW, Zero Electric Angle 3.36, Current Sensor Angle 5.68
[tilt] v1.0.6 — I 무응답(V만 응답)
```

- PAN `I` 응답에 **현재 센서각이 포함됨**(Current Sensor Angle) → 현재 PAN은 MCU 원점(센서각 = 오프셋).
- 명령표 정정: `T<rad>`는 **목표 이동 명령**(조회 아님). `R`은 MCU 전체 재부팅(결과적으로 토크 해제).
- ptz020은 현장 출고되어 비교 조회 불가.

## 5. 이번 조사에서 장비에 한 일

- **설정·파일 변경 없음.**
- 읽기 전용 조회: 로그, 파일 해시, 시리얼 수신 버퍼 읽기.
- MCU 조회 명령 송신: `V`, `I`, `E`, `A200` (조회 전용, 이동·저장 명령 아님). 11/02 `I`, `V` 재조회.
- onvif_srvd 재시작 1회(18:06:57) — MCU 시퀀스 측정용. 부팅 시와 같은 R/S 1회.
- 스냅샷 저장: `/home/ptz/vibcheck_20261029/settings.txt`

## 6. 다음 단계

1. ~~10/27 전원 확인~~ → 항상 PoE++ (완료). ~~떨림 축 확인~~ → PAN (완료).
2. 떨림 시작 시점 확인: 전원 직후(리눅스 부팅 전)인지, onvif 기동(R/S) 이후인지.
3. 부팅 시 PAN/TILT MCU 출력을 읽기 전용으로 기록하는 임시 로거로 떨림 구간 관찰(승인 후).
4. 다른 정상 유닛이 있으면 같은 `I`/`V` 조회로 PAN 펌웨어·Zero Electric Angle 비교.
5. 근거 확보 후 PAN 재보정(`CALIBRATE`) 여부 결정 — 보정값 덮어쓰기라 승인 필요. 시행 전 현재 값 기록(위 3.5).
6. `pantilt.py`는 onvif를 멈춘 상태에서만 쓰고, 운용 장비에서는 사용 자제(포트 이중 사용, 한계 초과 스윕).
