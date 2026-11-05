# 빌드 (mk3-basic)

## 전제

- 대상: aarch64 (Raspberry Pi). **카메라 본체에서 직접 빌드**한다 (ptz018 에서 검증, Debian 12 bookworm).
- 인터넷: 처음 패키지 설치와 upstream 클론 때만 필요. 이후 빌드는 오프라인 가능.
- 빌드 시간: 처음 전체 빌드 3~5분(gsoap 생성 코드), 이후 ServicePTZ.cpp 만 바뀌면 1분 안팎.

## 패키지

```bash
sudo apt-get install -y cmake g++ gsoap libgsoap-dev libcurl4-openssl-dev libmosquitto-dev libssl-dev zlib1g-dev
```

시스템 gsoap(2.8.124)에 링크한다(`-DUSE_SYSTEM_GSOAP=1`). 현장 원본 바이너리와 같은 라이브러리다.
**`-DWSSE_ON=1` 은 쓰지 않는다** — `libgsoapssl++` 에 링크되는데 현장 edge onvif-deps 에는 `libgsoap++` 만 있다 ([WSSE.md](WSSE.md)).

## 소스 준비

```bash
git clone https://github.com/KoynovStas/onvif_srvd.git
cd onvif_srvd
git checkout df09d0a                       # v2.0-29-gdf09d0a
git apply /path/to/이저장소/src/mk3-basic.patch
```

패치 대신 파일을 덮어써도 결과가 같다.

```bash
cp /path/to/이저장소/src/CMakeLists.txt  ./CMakeLists.txt
cp /path/to/이저장소/src/ServicePTZ.cpp  ./src/ServicePTZ.cpp
cp /path/to/이저장소/src/onvif_srvd.cpp  ./src/onvif_srvd.cpp
```

## 빌드

```bash
mkdir -p build && cd build
MK3_BUILD_INFO="mk3-basic $(date +%F) (upstream df09d0a + MK3 PTZ basic)" cmake -DUSE_SYSTEM_GSOAP=1 ..
make -j4
```

`MK3_BUILD_INFO` 는 `--version` / `--mcu-info` 에 찍히는 빌드 표시다. 없으면 빌드 시각이 들어간다.
환경변수로 넘긴다 — `cmake -D...` 로는 안 된다(아래 참고).

## 빌드 확인

```bash
./onvif_srvd --version          # onvif_srvd version 2.0.29 / MK3 build: ...
md5sum onvif_srvd               # 배포 기록용
```

## 참고

- `CMakeLists.txt` 가 `CMAKE_CXX_FLAGS` 를 직접 설정하므로 `cmake -DCMAKE_CXX_FLAGS=...` 는 덮어써진다.
  빌드 옵션은 환경변수(`MK3_BUILD_INFO`)로만 받는다.
- 경고 없이 빌드돼야 한다 (`-Wall -Wextra`).
- 배포 묶음(zip): `python3 tools/make_package.py --binary build/onvif_srvd` → [DEPLOY.md](DEPLOY.md)

## 참조 바이너리 (사내)

| md5 | 빌드 | 비고 |
|---|---|---|
| **`8a8bc609…`** | **v1.0** — mk3-basic v1.0 2026-11-05 | ptz018 검증. stream+q + ONVIF 계정 확인 ([WSSE.md](WSSE.md)) + 프리셋 이름 띄어쓰기·한글. libcrypto 직접 링크 (curl 이 이미 쓰는 라이브러리, 새 의존 없음) |
| `e4d4621a…` | (v1.0 이전 빌드) 계정 확인까지 | 프리셋 이름 띄어쓰기·한글 버그 있음 → `8a8bc609` 로 |
| `171ba6d8…` | (같은 코드, 빌드 이름 v1.1) | v1.0 으로 이름만 다시 빌드 |
| `d8d6c013…` | (v1.0 이전 빌드) 계정 헤더 받기만 | 확인은 안 함 — 아무 비밀번호로 PTZ 가능 → 쓰지 말 것 |
| `536e432e…` | mk3-basic 2026-11-04 stream+q | ptz018 검증. zoomfix + 스트리밍 모드(이동 감시) + v2.4+ 펌웨어 Q 기동 판정 ([PTZ_STREAMING.md](PTZ_STREAMING.md)) |
| `a6856dac…` | mk3-basic 2026-11-04 zoomfix | ptz018 검증 (03g + 줌 위치 읽기, 홈 저장, 계정 설정 읽기) |
| `2a450e4c…` | mk3-basic 2026-11-03g | ptz018 검증 (03f 대비 줌 응답 로그 제거) |
| `85ec44d9…` | mk3-basic 2026-11-03f | ptz018 검증 |
| `e688771b…` | v8 guard | .28 에서 검증 (스톨 가드). 이 저장소 이전 기록 |
| `110df0c5…` | v8 rangeonly | `-DSIMPLE_RANGE=1` |
| `448443…` | 현장 원본 | 부팅 때 R→S, 가드 없음 |
