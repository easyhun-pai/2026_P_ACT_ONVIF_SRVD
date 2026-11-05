onvif_setup — ONVIF(mk3-basic) 장비 시험 도구
설치 위치: /home/ptz/workspace/onvif_setup   (추가 설치·인터넷 불필요: 장비의 python3 + ffmpeg 사용)
카메라를 열고 HDMI·모니터를 연결할 필요 없음. PC에서 SSH로 실행하고 화면은 PC 브라우저로 본다.

1) 카메라 송출 확인 — 광각/줌 화면 + OK 표시
   ssh ptz@<장비IP>
   python3 ~/workspace/onvif_setup/onvif_cam_view.py
   → PC 브라우저에서 http://<장비IP>:8090   (Windows Terminal 등에서는 주소 Ctrl+클릭)
   종료: Ctrl+C
   (보는 동안 장비 CPU 약 30% 사용. 상세 상태: http://<장비IP>:8090/status)

2) 팬/틸트 기능 시험 (ONVIF 켠 채로, 장비에서)
   ssh ptz@<장비IP>
   cd ~/workspace/onvif_setup
   python3 onvif_pan_tilt.py --quick            # 틸트 3단계, 약 25초
   python3 onvif_pan_tilt.py                    # 틸트 0.2 rad 단계 전체(17단계), 약 2분
   python3 onvif_pan_tilt.py --quick --video    # 시험 + 카메라 화면(http://<장비IP>:8090) 같이
   옵션: --speed 1.0 (0.1~1, 1.0 = 펌웨어 최대 팬 3.0 rad/s), --cycles N, --tilt-step 0.2
   패턴: 틸트 단계마다 팬을 편도로 한 번 훑고, 끝에서 틸트만 바꿔 반대로 (지그재그)
   결과: 요약(OK/NEAR/FAIL, 오차, 이동 시간, 새 PTZ-ALERT, 총 소요 시간), logs/*.csv
   ※ 원본 pantilt.py는 모터 포트를 직접 쓰므로 onvif_srvd를 멈춰야 실행됨. 이 도구는 멈출 필요 없음.

3) 한 줄 이동 (ONVIF 켠 채로, 장비에서)
   python3 onvif_move.py 0 90                   # 팬 0°, 틸트 90° (기본 단위 도. 틸트 0° = 위, 90° = 수평 정면)
   python3 onvif_move.py 0 1.571 --rad          # 라디안으로
   python3 onvif_move.py 30 70 --speed 0.5      # 속도 0.1~1.0
   python3 onvif_move.py --preset 1             # 프리셋으로 (--list 로 목록)
   python3 onvif_move.py                        # 지금 각도만
   기본은 도착할 때까지 기다리고 결과 표시 (--no-wait 로 보내기만)

4) 줌 위치 시험 (ONVIF 켠 채로, 장비에서) — 줌이 잠깐 움직임
   sudo python3 onvif_zoom_test.py              # 웹 경로 줌 → ONVIF GetStatus/SetPreset/GotoPreset/RelativeMove/SetHome 확인
   시험 프리셋 ztest 는 끝에 지우고 줌은 시작 값으로 되돌림. 마지막 줄 VERDICT: PASS

5) 이동 감시(스트리밍 모드) 시험 — 이동 중/후 GetStatus 실측·MOVING/IDLE·Error 표시
   python3 onvif_stream_test.py move 0.5 1.2      # AbsoluteMove 후 12초 관찰 (라디안)
   python3 onvif_stream_test.py watch 10          # 움직이지 않고 관찰

6) 계정 헤더 처리 시험 (장비 안) — 조회만, 모터 안 움직임
   python3 onvif_wsse_test.py                     # 헤더 없음·계정 헤더 여러 형태 → 200, 모르는 필수 헤더 → 500
   장비 안(127.0.0.1)은 계정 확인을 하지 않으므로 PASS. 마지막 줄 == ALL PASS

7) 계정 확인 시험 (PC 에서) — 조회만, 모터 안 움직임
   python3 onvif_auth_test.py <장비IP> --password <웹 비밀번호>              # 맞는/틀린 계정, 이상한 헤더, 서버 생존
   python3 onvif_auth_test.py <장비IP> --password <웹 비밀번호> --lockout    # + 잠금 (이 PC 가 약 60초 잠김)
   python3 onvif_auth_test.py <장비IP> --password <웹 비밀번호> --expect-digest-fail   # 원문 파일 없는 장비
   마지막 줄 == ALL PASS. ODM 이 틀린 비밀번호로 켜져 있으면 그 PC 가 잠겨 결과가 틀어지니 ODM 을 닫고 할 것

8) 프리셋 이름 시험 (장비에서) — 모터 안 움직임. presets.txt 를 백업하고 끝나면 되돌림, 시험 중 onvif_srvd 한 번 재시작
   sudo python3 onvif_preset_name_test.py        # 띄어쓰기·한글·특수문자 이름, 깨진 줄, 삭제 뒤 유지, edge ptz_api 읽기
   마지막 줄 == ALL PASS

모터 상태만 볼 때:  onvif_srvd --mcu-watch   (Ctrl+C 종료)

시험 결과 CSV(logs/)는 7일 지나면 다음 시험 때 자동 삭제.
