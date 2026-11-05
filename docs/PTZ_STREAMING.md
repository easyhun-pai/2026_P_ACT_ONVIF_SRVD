# PTZ 스트리밍 모드 — 이동 감시 (2026-11-04)

요청(2026-11-03): "ptz 명령을 보내면 그대로 움직이고 마는데, 틀어져도 모르는 상황. 스트리밍 모드로 자세 변경 후 관측할 수 있으면 좋겠다."
해석(확인됨): 명령을 던지고 끝내지 않고 ① 이동 중·이동 후 **실측 자세를 계속 보고**, ② **도착할 때까지 확인**, ③ 도착 뒤 **틀어짐 감시**(필요하면 제한된 보정).

| 항목 | 값 |
|---|---|
| 빌드 | `mk3-basic 2026-11-04 stream+q`, md5 `536e432e3dc8e253434405b3ffbd6c13` |
| 기반 | mk3-basic + 줌 위치 수정(feat/zoom-position) |
| 검증 장비 | ptz018 (PAN v2.3.0 / TILT v1.0.6) |

## 동작

| 기능 | 내용 |
|---|---|
| 목표 기억 | AbsoluteMove / GotoPreset / GotoHome / RelativeMove / Stop / 연속이동 정지(Stop, 속도 0, 5초 자동정지) / 시작 위치 |
| 도착 확인 | 램프가 끝난 뒤 `arrive_timeout_s` 안에 두 축 모두 `arrive_tol_deg` 안 → `arrived`. 못 들어오면 `NOT_REACHED` |
| 틀어짐 감시 | 도착 뒤 `drift_tol_deg` 초과가 `drift_hold_s` 이어지면 `DRIFT` |
| 자동 보정 (기본 꺼짐) | 실측 → 목표로 느린 램프(속도 0.3). 목표당 최대 `correct_max` 회, 간격 `correct_gap_s`. 넘으면 `CORRECTION_FAILED` 로 **포기** (떨림 반복 방지). 모터 꺼짐·무응답이면 보정 안 함 |
| GetStatus | `Position` = **실측**(MCU 텔레메트리, 이동 중에도 MCU 가 계속 보냄. 2초 넘게 없거나 모터 꺼짐이면 명령값), `MoveStatus` = MOVING / IDLE, `Error` = `NOT_REACHED` / `DRIFT` / `MOTOR_OFF` / `NO_REPLY` / `CORRECTION_FAILED` |
| 플랫폼 | edge 가 1초마다 GetStatus 를 MQTT 로 보내므로 **edge 수정 없이 플랫폼 자세가 실측** (`/ptz/current` 확인) |
| 로그 | 상태가 바뀔 때만: `PTZ: arrived at ...`, `PTZ-ALERT: NOT_REACHED/DRIFT/CORRECTION_FAILED ...`, `PTZ-CMD: correction n/m ...` |
| 확인 | `/run/onvif_srvd/live` 와 `onvif_srvd --mcu-info` 에 `watch` 줄, `tools/onvif_setup/onvif_move.py` 에 GetStatus(실측/MoveStatus/Error) |

기존 보장 유지: 부팅·재시작 때 R 없음, 모터가 켜져 있으면 명령 0건, MCU 설정 쓰기 없음, 꺼짐·전원 문제는 경고만.

## 설정 `/var/lib/onvif_srvd/ptz_watch.conf`

없으면 기본값. 시작할 때 `PTZ: watch ...` 한 줄로 기록.

```
arrive_tol_deg   = 2      # 도착 허용 (deg)
arrive_timeout_s = 10     # 램프 끝 뒤 도착 대기
drift_tol_deg    = 3      # 도착 뒤 틀어짐 허용
drift_hold_s     = 3      # 이만큼 이어지면 DRIFT
correct          = 0      # 자동 보정 1/0
correct_max      = 2
correct_gap_s    = 10
status_position  = measured   # target 이면 GetStatus 를 예전처럼 명령값으로
q_run_bit        = 0x0001     # v2.4+ 펌웨어 Q 켜짐 비트 (아래)
```

**기본값을 요청서 제안(1° / 2°)에서 2° / 3° 로**: ptz018 정지 오차 팬 0.2°, 틸트 최대 1.4°, MCU 보고 단위 0.01 rad(0.57°) → 1° 면 틸트 오경보.

## 모터 펌웨어 v2.4+ 기동 판정 (라이다 신규 v2.5.1)

v2.5.1 은 모터가 꺼져 있어도 Sensor offset(EEPROM)을 보고해 'offset 0 = 꺼짐' 판정이 틀린다 (poe002 실측).
펌웨어 v2.4 이상이면 `Q` 상태로 판정한다 (시작 순서 V → T → Q → I, 운영 중 꺼짐 감시도 Q). 구 펌웨어는 기존 offset 판정.

`Q` 응답: `Q` + 16진 64자 = 32바이트 LE, 끝 2바이트 = 앞 30바이트 CRC-16/CCITT-FALSE.
[2..3] 플래그, [4..5] 목표 mrad, [6..7] 현재 mrad, [12..13] 전압 제한 mV, [14..15] 모터 온도 0.01°C, [18..19] 실내, [20..21] 과열 차단, [26..29] 가동 ms.

**켜짐 비트 0x0001 은 가정** (꺼진 상태 실측 0x0186 에서 0, 켜진 샘플 없음). 틀려도 안전 쪽: 꺼짐 판정 → S + 지금 자세 유지.
켠 뒤에도 0 이면 `PTZ-ALERT: ... Q running bit ... not set after arming` → 그 축 Q 꺼짐 감시 끔. 맞는 비트를 찾으면 `q_run_bit` 로 설정.
v2.5.1 실장비 확인 전. 라이다(Debian 13)는 장비에서 빌드해야 한다.

## 시험 (ptz018)

| 시험 | 결과 |
|---|---|
| 설치·재시작 | 모터 명령 0건, 시작 위치로 arrived |
| AbsoluteMove (1.0, 1.2) | 이동 중 MOVING + 실측 0.3초 단위 갱신, 3.6초 IDLE, arrived |
| 연속 이동 → Stop / → 속도 0 | 둘 다 멈춘 위치로 arrived |
| edge `/ptz/current` | 실측 |
| 허용 0.3° 강제 + 보정 on | NOT_REACHED → correction 1/2 → arrived (after correction) |
| 줌 시험 / 팬틸트 빠른 시험 | 9/9 PASS / CHECK — 틸트 위 끝(0°) 15초 뒤에도 3.4° 모자람 → NOT_REACHED (구 TILT 펌웨어 현상, 실제 검출) |
| v2.4+ Q 판정 | 단위 시험 (실측 3건 해석, CRC 틀림 거부, 버전 판별). 구 펌웨어 회귀 정상 (Q 안 보냄) |
| 손으로 밀기, 보정 꺼짐 (11-05) | 짧게 밀기 → 모터 보드가 스스로 복귀, DRIFT 없음. 3초 넘게(팬 34°) → `DRIFT`, GetStatus Error=DRIFT·위치 실측, 놓으면 `back to normal` |
| 손으로 밀기, 보정 켬 (11-05) | 틸트 30° → DRIFT → `correction 1/2` → `arrived (after correction)`. 계속 붙잡기(팬 42°) → `correction 2/2` → `CORRECTION_FAILED` 포기, 놓으면 `back to normal` |
| 미시험 | 실행 중 R(MOTOR_OFF), v2.5.1 실장비 |

## 확인 필요
1. 알람 경로: 지금은 GetStatus Error + 장비 로그. 별도 MQTT 토픽 필요 여부
2. 수치 2°/10초, 3°/3초. 틸트 위 끝 덜 붙는 장비 처리
3. 자동 보정 기본 off 유지 여부 — 11-05 손 밀기 시험: 보정 꺼져 있어도 놓으면 모터 보드가 목표로 되돌림 → off 권장
4. 엔코더 기준이라 브래킷 미끄러짐·장비째 회전은 못 잡음
5. 대상 장비 (서울 현장 = 라이다?)
6. GetStatus 가 실측으로 바뀌어 추적기 입력이 달라짐 — 문제 시 `status_position = target`
