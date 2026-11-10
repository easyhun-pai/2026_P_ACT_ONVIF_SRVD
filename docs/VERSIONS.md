# 버전 기록

SW 버전 = 바이너리 md5 앞 8자리. 장비에서 `md5sum $(which onvif_srvd) | cut -c1-8`, 빌드 이름은 `onvif_srvd --version`.

## 버전

| 버전 | 날짜 | md5 | 빌드 이름 (`MK3_BUILD_INFO`) | 내용 | 검증 |
|---|---|---|---|---|---|
| **v1.1.0** | 2026-11-10 | `a8e37f1f` | mk3-basic v1.1.0 2026-11-10 | v1.0.0 + **모터 헬스** (Q 펌웨어 v2.4+ 축: 추정 온도·발열·Vq·트립 → live·`motor_health.json`·MQTT `<topic>_health`·`PTZ-HEALTH` 로그·경보, GetStatus `MOTOR_OVERHEAT`) ([MOTOR_GUARD.md](MOTOR_GUARD.md)). 브랜치 `feat/motor-health` | poe002(v2.5.1): 출력·경보·전 범위. ptz018(Pro): 회귀 14/14 (시험 빌드 `3d4d8118`, 같은 소스) |
| **v1.0.0** | 2026-11-05 | `8a8bc609` | mk3-basic v1.0 2026-11-05 | 아래 stream+q + **ONVIF 계정 확인** (admin + 웹 비밀번호, Digest·Text) + edge 패치 ([WSSE.md](WSSE.md)) + **프리셋 이름 띄어쓰기·한글** | ptz018: 계정 114건 + 프리셋 이름 25건 PASS, ODM 실기 |
| (중간) | 2026-11-05 | `e4d4621a` | mk3-basic v1.0 2026-11-05 | 계정 확인까지. 프리셋 이름에 띄어쓰기가 있으면 뒤 프리셋이 밀려 망가짐, 한글 이름 깨짐 → `8a8bc609` 로 바꿀 것 | ptz018: 114건, ODM 실기 |
| (중간) | 2026-11-05 | `171ba6d8` | mk3-basic v1.1 2026-11-05 | v1.0 과 같은 코드, 빌드 이름만 v1.1 → v1.0 으로 합침 | ptz018 |
| (중간) | 2026-11-05 | `d8d6c013` | mk3-basic v1.0 2026-11-05 | stream+q + 계정 헤더 받기만 — **확인은 안 함** (아무 비밀번호로 PTZ 가능). 쓰지 말 것 | ptz018: 자동 시험 33/33, ODM 계정 등록 → 정보·PTZ·프리셋·영상 |
| stream+q | 2026-11-04 | `536e432e` | mk3-basic 2026-11-04 stream+q | zoomfix + **이동 감시(스트리밍 모드)** + **v2.4+ 펌웨어 Q 기동 판정** ([PTZ_STREAMING.md](PTZ_STREAMING.md)) | ptz018: 이동·Stop·보정 시험, 11-05 손 밀기 시험 |
| zoomfix | 2026-11-04 | `a6856dac` | mk3-basic 2026-11-04 zoomfix | 03g + **줌 위치를 줌카메라에서 읽기**, 홈 위치 저장, 줌카메라 계정 설정에서 읽기 | ptz018: 줌 시험 9/9 |
| 03g | 2026-11-03 | `2a450e4c` | mk3-basic 2026-11-03g | mk3-basic (상태 판정 기동, 콜드부팅 30초 대기) + 줌 응답 로그 제거 | ptz018 |
| 03f | 2026-11-03 | `85ec44d9` | mk3-basic 2026-11-03f | mk3-basic 첫 검증판 | ptz018 |
| v8 guard | 2026-07-29 | `e688771b` | - | 스톨 가드 (이전 개조, [HISTORY.md](HISTORY.md)) | .28 |
| 현장 원본 | 2026-07-28 | `448443cd` | - | 부팅 때 R→S, 가드 없음. edge onvif-deps 기본 | - |

아래 순서로 쌓인다: 원본 upstream `df09d0a` → mk3-basic(03f·03g) → zoomfix → stream+q → 계정 헤더 받기 → 계정 확인 → **v1.0** (+ 프리셋 이름).
태그 `v1.0.0` 은 계정 확인·프리셋 이름까지 넣은 main 커밋 (2026-11-10 에 `v1.0` 에서 이름을 바꿈, edge 와 같은 3자리 형식). 잠깐 있던 태그 `v1.1` 은 지웠다 (2026-11-05).
버전 규칙 (2026-11-10~): `주.부.수` — 호환이 깨지면 주, 기능 추가는 부, 버그 수정·작은 변경은 수. `v1.1.0` (모터 헬스)은 브랜치 `feat/motor-health` 에 있고 main 에는 아직 안 합침.
배포 묶음: `python3 tools/make_package.py --binary <onvif_srvd>` → `onvif_mk3_basic_<날짜>_<md5>.zip`.

## 정리한 브랜치 (2026-11-05)

v1.0 을 main 에 합치며 작업 브랜치를 지웠다. 내용은 모두 main 에 있다.
main 위로 다시 쌓아서 커밋 번호가 바뀌었다 (메시지·내용 같음).

### 사내 저장소 (비공개)

| 브랜치 | 마지막 커밋 | 내용 | main 에서 |
|---|---|---|---|
| `feat/zoom-position` | `20f0da1` | 줌 위치 수정 (zoomfix) | 아래 표 |
| `feat/ptz-streaming` | `17aef37` | zoomfix + 스트리밍 모드 + Q 기동 판정 (stream+q) | 아래 표 |

| 브랜치 커밋 | 메시지 | main 커밋 |
|---|---|---|
| `882362d` | chore: 줄바꿈 LF 고정(.gitattributes), _workspace/ 무시 | `ea22809` |
| `43cc0c7` | feat(ptz): 줌 위치를 줌카메라에서 읽기, 홈 위치 저장, 줌카메라 계정 설정에서 읽기 | `25fd049` |
| `cde88b4` | feat(tools): onvif_zoom_test.py — 줌 위치 시험 | `54eea1d` |
| `0508923` | docs: 줌 위치 수정 설계·시험, edge onvif-deps 덮어쓰기 주의 | `e67d4e6` |
| `20f0da1` | docs: 표현 정리 (zoom 브랜치) | main `3e0ce9c` 과 같은 수정이라 합침 |
| `0ebf04a` | feat(ptz): 스트리밍 모드 — 목표 기억, 도착 확인, 틀어짐 감시, 제한된 보정 | `b497efb` |
| `17aef37` | docs, tools: 스트리밍 모드 설계·시험, onvif_move.py GetStatus 표시, onvif_stream_test.py | `9c2ca93` |

### 공개 저장소 (easyhun-pai)

| 브랜치 | 마지막 커밋 | 내용 |
|---|---|---|
| `feat/zoom-position` | `962af24` | 줌 위치 수정 (공개용 정리본). v1.0 정리본 커밋에 포함 |

## 다음 버전에서 할 것
- edge onvif-deps.tar.gz 에 v1.0 반영 (지금 edge 패키지 업데이트는 원본 `448443` 으로 덮어씀)
- 현장 NVR 한 종류로 계정 등록 확인
- 모터 펌웨어 v2.5.1 실장비에서 Q 켜짐 비트 확인 — [PTZ_STREAMING.md](PTZ_STREAMING.md)
