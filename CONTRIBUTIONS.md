# Contributions — P-ACT PTZ 카메라 ONVIF 서버 (mk3-basic)

> 이 저장소는 사내 저장소에서 진행한 작업을 공개용으로 정리한 최종 스냅샷이다.
> 비밀번호·사내 주소·장비 고유 ID 는 지웠다. 사내에서는 기능 단위 커밋으로 나눠 반영했다.

| 항목 | 내용 |
|---|---|
| 기간 | 2026-10-27 ~ 2026-11-03 |
| 역할 | 담당 — 현장 A/S 원인 분석, ONVIF 서버 재설계·구현, 실기기 검증, 시험·배포 도구, 문서 |
| 대상 | P-ACT(MK3) PTZ 카메라 — Raspberry Pi CM5 + STM32 FOC BLDC 짐벌 모터 2축(팬/틸트) + 광각·줌 카메라 |
| 기술 | C++11 (gSOAP ONVIF, POSIX 시리얼, pthread, libcurl, MQTT), Python 3, systemd / journald, NetworkManager, ffmpeg |

## 1. 문제

출고 장비 한 대가 **콜드부팅 때마다 모터가 3~7초간 떨린다**는 A/S 가 들어왔다.
"ONVIF 업데이트 이후 생겼다"는 보고였고, 원인이 SW 인지 장비인지부터 불분명했다.

## 2. 원인 분석

- 부팅 로그, 모터 보드(MCU) 시리얼 출력, Pi 리셋 원인 레지스터를 수집해 **SW 가 매 부팅 같은 명령(R→S)을 같은 타이밍에 보낸다**는 것을 확인
- 같은 명령을 최신 펌웨어 장비에 보내 비교 → 떨림 없음
- 떨림은 S 이후 **MCU 가 처진 틸트를 0° 까지 스스로 들어 올리는 구간**에서만 발생, 해당 장비의 **틸트 펌웨어가 구버전**
- 결론: 근본 원인은 펌웨어/기구. SW 로는 그 동작을 **피하는** 방향으로 설계
- 근거 문서: [docs/incidents/EVIDENCE-261102-boot-vibration-not-sw.md](docs/incidents/EVIDENCE-261102-boot-vibration-not-sw.md)

## 3. 설계 · 구현 — ONVIF 서버 mk3-basic

upstream `KoynovStas/onvif_srvd` 를 기준으로 PTZ 서비스(`src/ServicePTZ.cpp`)를 다시 작성했다.

| 무엇을 | 어떻게 | 왜 |
|---|---|---|
| **부팅 시 모터 리셋 제거** | R 을 보내지 않고, 축마다 값 없는 `T`(상태 조회)로 기동 여부를 판정. 켜져 있으면 명령 0건 | Pi 재부팅 시 MCU 는 기동 상태를 유지함을 실측 |
| **상태 판정 순서** | V(버전) → T(상태) → I(설정). I 를 먼저 보내면 꺼진 MCU 가 offset 을 채워 오판 | 펌웨어 동작을 실측으로 확인 |
| **콜드부팅 판별** | Pi 리셋 원인 레지스터(`rsts`: 0x1000 전원 / 0x1020 재부팅) + 부팅별 시작 표식 | 콜드부팅 직후 MCU 상태값만으로는 오판 사례 있음 |
| **현재 자세 그대로 기동** | 콜드부팅 30초 뒤 두 축 동시 S, 직후 3초간 현재 각도를 20ms 마다 목표로 스트리밍 → 그 자리에서 힘만 들어감 | 떨림을 일으키던 '0° 로 들어 올리기' 자체를 없앰 |
| **각도 계산** | 저장된 센서 offset 으로 원시각 → 실제각, 바퀴 누적값을 [−π, π] 로 정규화 | 누적값을 범위 밖으로 오판해 팬이 108° 회전하던 버그 수정 |
| **시리얼 독점 + 수신 스레드** | `flock` + `TIOCEXCL`, 전용 reader 스레드가 모든 MCU 출력 파싱 | 다른 프로세스와의 동시 제어로 모터가 휘청이던 사고 재발 방지 |
| **이상 감지, 자동 재시도 없음** | MCU 자체 재부팅 배너·0.5초 주기 상태 조회로 꺼짐/목표 미유지/무응답 감지 → `PTZ-ALERT` 로그만 | 전원 문제 시 꺼짐/켜짐 반복 방지 |
| **관측성** | `PTZ-CMD`(보낸 명령과 이유)·`PTZ-MON`·`PTZ-ALERT` 로그, `/run/onvif_srvd/live`, `onvif_srvd --mcu-info` / `--mcu-watch` | 현장에서 펌웨어 버전·실시간 각도 확인 |
| **기타** | 기동 전 이동 요청 보관 후 실행, ONVIF AbsoluteMove `Speed` 지원, 줌 카메라 응답 로그 제거, 출력 ASCII 화 | 요청 유실 방지, 시험 시간 단축, 로그 용량, 터미널 호환 |

upstream 에 바로 적용되는 패치: [src/mk3-basic.patch](src/mk3-basic.patch) · 설계 상세: [docs/MK3_BASIC.md](docs/MK3_BASIC.md)

## 4. 검증 (실기기)

| 시험 | 결과 |
|---|---|
| 콜드부팅 7회 (거꾸로 매단 자세 포함) | **떨림 3~7초 → 0**, 움직임 없음 |
| Pi 재부팅 / 서비스 재시작 | 모터 명령 **0건** |
| 실행 중 모터 보드 강제 리셋 | 0.03초 내 경고, 재시도 없음 |
| 기동 전(부팅 30초 내) 이동 요청 | 기동 직후 실행, 정상 도달 |
| 팬/틸트 스윕 | 지점별 오차 팬 평균 0.2°, 경고 0건 |
| 부팅 중 "딱딱" 소리 | SW 를 끈 콜드부팅에서도 발생 → 하드웨어 자체 소리로 SW 원인 배제 |

중간 단계마다 장비에서 빌드가 되는지, 패치가 upstream 에 그대로 적용되는지 확인했다.

## 5. 시험 · 배포 도구

| 도구 | 내용 |
|---|---|
| [tools/onvif_setup/onvif_cam_view.py](tools/onvif_setup/onvif_cam_view.py) | 장비 안에서 ffmpeg 로 두 카메라를 MJPEG 로 변환 → PC 브라우저 한 화면에 광각/줌 + OK 표시. 카메라 분해·HDMI 연결 없이 송출 확인 |
| [tools/onvif_setup/onvif_pan_tilt.py](tools/onvif_setup/onvif_pan_tilt.py) | ONVIF 를 끄지 않고 팬/틸트 지그재그 스윕, 지점별 도착·오차·시간, PASS/CHECK 판정, CSV. 기존 왕복 방식 대비 **59초 → 24초** |
| [tools/onvif_setup/onvif_move.py](tools/onvif_setup/onvif_move.py) | 한 줄 이동 (도 단위, 프리셋, 도착 확인) |
| [tools/make_package.py](tools/make_package.py) | 바이너리·스크립트·시험 도구·설치 절차를 zip 하나로. 표준 라이브러리만 사용 (PC OS 무관) |

모두 장비의 python3·ffmpeg 만 쓰고, 추가 설치·인터넷 없이 동작한다.

## 6. 문서

- 하드웨어 실측 사실 정리·정정 — [docs/HARDWARE.md](docs/HARDWARE.md) 9절
- 빌드·배포(설치/롤백/긴급 정지)·운용 문서 — [docs/BUILD.md](docs/BUILD.md), [docs/DEPLOY.md](docs/DEPLOY.md), [docs/OPERATIONS.md](docs/OPERATIONS.md)
- 이슈 트래커·증빙 — [docs/incidents/](docs/incidents/)
- 현장 테스트 가이드에 SW·모터 펌웨어 버전 확인 절차 반영

## 7. 그 외

- 부팅 중 네트워크 이벤트마다 서비스가 재시작되던 문제 수정 (NetworkManager dispatcher)
- DHCP 실패 시 내부 카메라망 IP 로 서비스가 뜨던 문제 수정 (`deploy/onvif_start.sh`)

## 남은 과제 (인계)

- 구버전 틸트 펌웨어 업데이트와 틸트 브래킷 기구 점검 (근본 원인)
- 빠른 이동 시 틸트 미세 떨림 — 작은 스텝 램프와 펌웨어 튜닝 영향으로 추정
- edge 패키지 정식 반영
