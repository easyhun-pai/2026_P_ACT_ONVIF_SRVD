# ONVIF 계정 헤더(WS-Security) 받기 (2026-11-05, v1.0)

## 문제
ONVIF Device Manager(ODM)·NVR 은 계정을 `wsse:Security` 헤더(`mustUnderstand="1"`)로 보낸다.
onvif_srvd 는 WSSE 없이 빌드돼 이 헤더를 몰라 모든 요청을 거부했다:

```
SOAP-ENV:MustUnderstand — The data in element 'Security' must be understood but cannot be processed
```

- 계정을 넣으면 ONVIF 가 거부, 계정을 빼면 영상(RTSP)이 401 → ODM·NVR 로 PTZ 와 영상을 같이 못 씀
- 원본(07-28 배포본, `448443`)부터 같음

## 수정 (1단계: 받아 넘기기)
`src/onvif_srvd.cpp` `init_gsoap()` 에 gSOAP `soap->fignore` 콜백:

| 받은 요소 | 동작 |
|---|---|
| 헤더 안 `Security` (ns 에 `secext`: OASIS wss 2004/01, 구 2002/07), mustUnderstand | **통과** (계정 확인 안 함) |
| 그 밖의 모르는 mustUnderstand 헤더 | 예전처럼 `MustUnderstand` fault |
| mustUnderstand 아닌 모르는 요소 | 예전처럼 무시 |

- 보안 수준은 예전과 같다: ONVIF 는 원래 계정 검사가 없고, 영상은 edge 가 admin + 영상 비밀번호로 확인한다.
- 헤더 없는 요청(edge `ptz_api`, 시험 도구)은 그대로 받는다.
- Security 내용은 읽지 않으므로 응답에 계정이 되돌아가지 않는다.
- 처음 받을 때 한 번 로그: `ONVIF: WS-Security header accepted (credentials not checked)`

**`-DWSSE_ON=1` 을 쓰지 않은 이유**: `libgsoapssl++` 에 링크되는데 현장 edge onvif-deps(`/usr/local/lib`)에는
`libgsoap++` 만 있어 바이너리만 바꾸면 실행되지 않을 수 있다. 이 수정은 링크 라이브러리가 예전과 같다.

## 시험 (ptz018, 빌드 `d8d6c013`)

| 요청서 시험 | 결과 |
|---|---|
| 1. 헤더 없는 요청 → 200 | 통과 |
| 2. 계정 헤더 붙은 GetDeviceInformation, GetProfiles, GetStreamUri, PTZ GetStatus → 200 | 통과 (`onvif_wsse_test.py` 33/33, 장비 안·PC 둘 다) |
| 3. ODM 에 admin + 웹 비밀번호로 추가 → 장비 정보, PTZ, 프리셋, 영상 | 통과 |
| 4. edge 웹 화면·API PTZ, 플랫폼 PTZ | API 정상 |
| 5. 현장 NVR 등록 | 안 함 (선택) |

- 고치기 전(`536e432e`): 계정 헤더 붙은 17건 모두 500 `MustUnderstand` (요청서 재현)
- 모르는 필수 헤더, 이름만 Security(다른 ns) → 500 유지. 응답에 계정 노출 없음
- 재시작 때 모터 명령 0건, 이동 감시·줌 위치 그대로

## ODM 으로 확인하는 법 (PC)
1. ODM 실행 → 같은 망이면 장비가 목록에 자동으로 뜸 (장비의 `wsdd`). 안 뜨면 **Add** → `http://<장비IP>:1000/onvif/device_service`
2. 왼쪽 위 로그인: `admin` + **영상 비밀번호** → Refresh
   - 영상 비밀번호 = 웹에서 직접 정한 비밀번호, 정하지 않았으면 시리얼 (정한 뒤에는 시리얼로 영상 안 열림)
3. 장비 선택 → 오류 없이 메뉴가 뜨면 ONVIF 통과 → **Live video**(영상), **PTZ control**(방향·프리셋)
- 영상이 `NO SIGNAL` 이면 장비 `journalctl -u edge-settings | grep "영상 인증"` — `wrong-credentials` 면 비밀번호가 틀림.
  5번 틀리면 그 PC IP 가 60초 잠기고, ODM 이 2초마다 다시 시도해 잠금이 이어진다 → Live video 를 닫고 1분 뒤 다시.
- ODM 2.2.250 에는 장비 지우기(Remove) 버튼이 없다. 계정은 장비별이 아니라 왼쪽 위 로그인 하나로 모든 장비에 쓴다.

## 2단계 (나중, 결정 필요) — 실제 계정 확인
- admin + 웹 비밀번호, PasswordDigest·PasswordText 둘 다, GetSystemDateAndTime 등은 로그인 전 허용
- 위 `fignore` 자리에서 UsernameToken 을 읽어 확인할 수 있다
- 결정할 것: PasswordDigest 확인에는 비밀번호 원문이 필요하다 (edge 는 해시만 저장) → 원문 보관 여부
