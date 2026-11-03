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

모터 상태만 볼 때:  onvif_srvd --mcu-watch   (Ctrl+C 종료)

시험 결과 CSV(logs/)는 7일 지나면 다음 시험 때 자동 삭제.
