# .205 `/api/ptz` 휘청거림 원인 분석 — poelidar-2707-001 (<field-unit-205>)

작성일: 2026-08-24 · 상태 확인만 수행(모터·서비스 조작 없음)

## 1. 증상

`http://<field-unit-205>/api/ptz` 로 PTZ 명령을 보내면 카메라가 목표로 가지 않고 **휘청거리기만** 함.

## 2. 현재 배포 상태

| 항목 | 값 |
|---|---|
| onvif_srvd 바이너리 | `110df0c5` — **rangeonly** (각도제한 O / 스톨가드·무장해제 X) |
| onvif 서비스 | active + enabled (8/13에 disable 해둔 것이 다시 enable됨) |
| onvif 시리얼 점유 | `/dev/ttyAMA0`(pan), `/dev/ttyAMA2`(tilt) 를 onvif_srvd(pid 1022)가 열어 둠 |
| `/api/ptz` 서버 | `/home/poe/edge/lidar_web.py` (edge-lidar-web.service, :80) |
| lidar_web.py 수정 이력 | 8/21 22:39 (`bak_ptz`), 8/24 09:50 (`bak_preset`) — 프리셋/패트롤 기능 추가된 버전 |
| range.conf | pan ±135°, tilt 0~90° |
| 부팅 후 onvif 로그 | range 로드 → 위치복원 (0.080, 0.688) 완료. 이후 /api/ptz 호출 로그 없음 |

## 3. 원인 — 모터 시리얼 포트에 컨트롤러가 2개

`lidar_web.py`의 `PTZController`(34~110행)는 onvif를 거치지 않고 **시리얼을 직접 열어 `R`/`S`/`T`를 전송**한다. 같은 포트를 onvif_srvd가 이미 소유·제어 중이므로 두 프로세스가 한 모터에 동시에 명령을 쓰는 구조가 된다.

```python
# lidar_web.py (발췌)
PAN_PORT, TILT_PORT, BAUD = "/dev/ttyAMA0", "/dev/ttyAMA2", 115200
PAN_MIN, PAN_MAX = -2.8, 2.8          # onvif 범위(±2.356)와 불일치
STEP_RAD, STEP_DT = 0.05, 0.01

def _ensure_init(self):               # 최초 명령 시
    self._sp = serial.Serial(PAN_PORT, BAUD, timeout=1)
    self._st = serial.Serial(TILT_PORT, BAUD, timeout=1)
    self._send(self._sp, "R"); self._send(self._st, "R")   # ← MCU 리셋·재정렬
    time.sleep(2.5)
    self._send(self._sp, "S"); self._send(self._st, "S")
    self._pan, self._tilt = 0.0, 0.0                       # ← 자기 기준 0,0 가정

def _glide(self, ser, cur, target):
    self._send(ser, "S")                                   # ← 매 이동마다 S 재전송
    ...T 보간 전송...
```

### 휘청거림이 만들어지는 순서

1. **첫 `/api/ptz` 호출 시 `R` 전송** → MCU 리셋·재정렬로 토크가 순간 빠지고 각도 기준이 0으로 재설정됨. onvif_srvd는 이를 모르므로 onvif가 알고 있는 위치(부팅 복원값 0.080/0.688)와 실제 프레임이 어긋남.
2. **매 이동마다 `S` 재전송** → `S`도 MCU 재초기화("Align sensor")를 유발(벤치 실측). 명령마다 정렬 동작이 끼어들어 **툭툭 튀는 움직임**이 됨.
3. lidar_web은 자기 dead-reckoning(0,0 기준)으로 T 램프를 쏘지만 실제 모터는 onvif가 옮겨둔 위치에 있음 → 램프의 첫 T들이 실제 위치와 크게 어긋남 → 급격한 오차 → 휘청.
4. ODM/UI가 onvif(:1000)로도 명령을 내리면 두 프로세스의 T 스트림이 뒤섞임.
5. 범위 불일치(lidar_web pan ±2.8 vs onvif ±2.356)로 한쪽이 허용하는 각도를 다른 쪽이 막는 구간 존재.

부팅(11:45) 이후 `/api/ptz` 호출 기록이 없어 충돌 순간의 로그는 없으나, 코드 경로상 호출 시 1~3은 반드시 발생한다.

### 참고
8/12에 .162(<field-unit-162>)의 lidar_web은 동일 충돌 때문에 **ONVIF 클라이언트 방식**(시리얼을 열지 않고 `127.0.0.1:1000`에 AbsoluteMove)으로 교체했음. .205의 8/21 수정본은 다시 직접 시리얼 방식이다.

## 4. 해결 방향 (미적용)

| 방안 | 내용 | 장단점 |
|---|---|---|
| **A. 권장** | lidar_web `PTZController`를 .162와 같은 ONVIF 클라이언트 백엔드로 교체 (move/home/goto 인터페이스 유지, 시리얼 미사용) | 모터 소유자 onvif 하나로 일원화, R/S 남발 제거, 범위·복원·프리셋 모두 onvif가 관리. ODM 제어와 공존 |
| B. 대안 | onvif_srvd 정지·disable, lidar_web이 시리얼 단독 소유 | 구조 단순. 단 ODM/ONVIF 제어 불가, 부팅 위치복원·범위관리 없음, `S` 재전송 튐은 그대로 |

어느 쪽이든 **한 모터에 컨트롤러는 하나**가 원칙. 8/21 수정 작업자와 조율 후 적용 권장.

## 5. 관련 파일

- `/home/poe/edge/lidar_web.py` (현재), `.bak_ptz_20260821_2239`, `.bak_preset_20260824_0950`
- `/usr/local/bin/onvif_srvd` (rangeonly), `/usr/local/bin/onvif_srvd.guard.bak` (스톨가드 버전)
- `/var/lib/onvif_srvd/range.conf`, `position.txt`
- 관련 문서: `INCIDENT-205-tilt-over90.md`
