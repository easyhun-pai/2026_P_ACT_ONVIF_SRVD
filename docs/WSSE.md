# ONVIF 계정 (WS-Security) — v1.0 받기, v1.1 확인 (2026-11-05)

## 문제
ONVIF Device Manager(ODM)·NVR 은 계정을 `wsse:Security` 헤더(`mustUnderstand="1"`)로 보낸다.

| 버전 | 계정을 넣으면 | 계정을 빼면 |
|---|---|---|
| 원본 ~ stream+q | ONVIF 가 모든 요청 거부 (`MustUnderstand`) | ONVIF 는 되지만 영상(RTSP) 401 |
| v1.0 | ONVIF 받음, **확인은 안 함 → 아무 비밀번호로 PTZ 가능** (영상만 막힘) | 같음 |
| **v1.1** | **admin + 웹 비밀번호 확인** — 맞으면 PTZ·영상, 틀리면 둘 다 거부 | 밖에서는 거부 (장비 안은 허용) |

## v1.1 규칙 (`src/onvif_srvd.cpp` `mk3_authorize`)

| 요청 | 처리 |
|---|---|
| 장비 안 (127.x) | 계정 없이 허용 — edge 웹·플랫폼 PTZ(`ptz_api`), 시험 도구 |
| 로그인 전 조회 (ONVIF PRE_AUTH) | 계정 없이 허용 — GetSystemDateAndTime, GetCapabilities, GetServices, GetServiceCapabilities, GetWsdlUrl, GetHostname, GetEndpointReference |
| 밖에서, 계정 없음 | 거부 (실패로 세지 않음) |
| 밖에서, admin + 맞는 비밀번호 | 허용 — PasswordDigest `Base64(SHA1(Nonce + Created + 비밀번호))`, PasswordText 둘 다 |
| 틀린 비밀번호·아이디 | 거부, IP 별 실패 기록. **5번 틀리면 60초 잠금**, 잠긴 뒤로도 틀릴 때마다 다시 잠금 (edge 영상과 같은 규칙, 카운터는 따로) |

거부 응답: SOAP fault `ter:NotAuthorized` (HTTP 400). 로그 `ONVIF-AUTH: DENIED <요청> from <IP> (<이유>)`.

**비밀번호 기준 = 영상(edge `_verify_stream_password`)과 같음**
- 웹에서 비밀번호를 정했으면 그것만 (`/home/ptz/edge/.device_auth` 의 `sha256("장비ID:비밀번호")`)
- 정하지 않았으면 장비 시리얼 (`/var/lib/onvif_srvd/device_id` 의 `MK3-` 뒤)

**Digest 와 비밀번호 원문**
- edge 는 해시만 저장 → Digest 확인에는 원문이 필요
- edge 패치(`deploy/edge_onvif_auth_patch.py`): 웹 비밀번호 변경 때 `/var/lib/onvif_srvd/onvif_auth` (root 600)에 원문, 초기화 때 삭제
- onvif 는 원문이 **해시와 맞을 때만** 쓴다 → 옛 값·오타가 남아도 안전
- 원문이 없으면: PasswordText 는 해시로 확인, Digest 는 거부(`digest-needs-password-file`, 실패로 세지 않음) → 웹 비밀번호를 한 번 다시 저장

**비상용**: `/var/lib/onvif_srvd/onvif_auth_off` 가 있으면 확인 안 함 (v1.0 동작). 재시작 불필요.

**하지 않는 것 (알고 둠)**
- Created 시각 검사·Nonce 재사용 검사 없음 — NVR 과 장비 시계가 어긋나도 되게. 대신 잠금과 HTTPS 아님에 유의(같은 망 도청 시 Digest 재사용 가능)
- 요청 앞 64KB 안의 헤더만 본다 (그 뒤에 있으면 계정 없음으로 거부)
- Text 비밀번호는 그대로 비교 (앞뒤 공백도 비밀번호)

## 구현
- `soap->fignore`: 헤더 안 `Security`(ns 에 `secext`)만 이해한 것으로 넘김, 다른 모르는 필수 헤더는 예전처럼 `MustUnderstand`
- `soap->frecv` 를 감싸 받은 원문 앞 64KB 보관 → 헤더(Body 앞) 안의 `Security/UsernameToken` 을 접두사 무관하게 읽음 (XML 문자참조 처리)
- 본문 첫 요소 이름(`soap_peek_element`)으로 PRE_AUTH 판단, 거부면 서비스로 넘기지 않고 fault
- 계정 파일은 요청마다 읽음 (비밀번호를 바꾸면 바로 적용, 재시작 불필요)
- `-DWSSE_ON=1` 미사용: `libgsoapssl++` 가 현장 onvif-deps 에 없음. SHA1/SHA256 은 libcrypto (curl 이 이미 쓰는 라이브러리)

## 시험 (ptz018, 빌드 `171ba6d8`) — 114건 PASS

| 시험 | 도구 | 결과 |
|---|---|---|
| 계정 없음 / 맞는 계정(Digest·Text, 접두사 o, SOAP 1.1, mustUnderstand 없음, Nonce 없음, Type 없음, 문자참조, 아이디 공백, wsa 같이, 오래된 Created, 재사용) / 틀린 계정 / 이상한 헤더(UsernameToken 없음, Body 안, Digest 를 Text 로, 빈 비밀번호, 공백, 다른 ns, 모르는 필수 헤더) / 깨진 XML·200KB 쓰레기·70KB 헤더·중간 끊김 뒤 생존 / 잠금·풀림 | `tools/onvif_setup/onvif_auth_test.py` (PC) | 원문 파일 있음 43/43 (잠금 포함), 없음 40/40 |
| 원문 파일 옛 값 / 끝 줄바꿈 / 웹 비밀번호 안 정함(시리얼) / `.device_auth` 없음 / 특수문자·한글 비밀번호 / 장비 ID 없음(밖 거부, 안 허용) / 비상 해제 파일 | `tools/auth_tests/scenario_test.py` (PC, ssh) | 17/17, 원래 파일로 되돌림 |
| edge 웹 비밀번호 변경 → 원문 파일(600 root) → ONVIF 새 비밀번호 OK·옛 거부 / 되돌리기 / 초기화 → 파일 삭제·시리얼 OK → 다시 설정 | `tools/auth_tests/edge_e2e_test.py` (PC) | 14/14, 원래 비밀번호로 되돌림 |
| 장비 안 헤더 처리, edge `/ptz/current`, 재시작 모터 명령 0건 | `onvif_wsse_test.py` (장비) | PASS |

시험 중 고친 버그: 원문 파일이 없어 Digest 를 확인 못 한 것까지 실패로 세서 ODM 이 접속 몇 번 만에 스스로 잠김 → 세지 않게.

## ODM 으로 확인하는 법 (PC)
1. ODM 실행 → 같은 망이면 장비가 목록에 자동으로 뜸 (장비의 `wsdd`). 안 뜨면 **Add** → `http://<장비IP>:1000/onvif/device_service`
2. 왼쪽 위 로그인: `admin` + **웹 비밀번호** (정하지 않았으면 시리얼) → Refresh
3. 장비 선택 → **Live video**(영상), **PTZ control**(방향·프리셋)
4. 틀린 비밀번호로 로그인하면 장비 선택 때 오류, PTZ·영상 모두 안 됨이 정상
- 틀린 비밀번호로 ODM 을 켜 두면 2초마다 다시 시도해 그 PC IP 가 계속 잠긴다 (ONVIF·영상 따로). 로그아웃하거나 ODM 을 닫고 1분 뒤 다시
- 영상 문제는 장비 `journalctl -u edge-settings | grep "영상 인증"`, ONVIF 는 `journalctl -u onvif_srvd | grep ONVIF-AUTH`
- ODM 2.2.250 에는 장비 지우기(Remove) 버튼이 없다. 계정은 왼쪽 위 로그인 하나로 모든 장비에 쓴다.
