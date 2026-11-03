#!/usr/bin/env python3
"""
팬/틸트 스윕 기능 시험 — 장비에서 실행, ONVIF를 끄지 않음 (추가 설치·인터넷 불필요)

원본 pantilt.py처럼 틸트 단계마다 팬을 훑되, 왕복 대신 편도 지그재그(팬 끝에서 틸트만 바꿔 반대로)로 시간을 절반으로 줄였다.
  - 모터 보드에 직접 쓰지 않는다 → onvif_srvd를 멈출 필요 없음, R/S 없음(모터를 끄지 않음)
  - 범위는 펌웨어 한계 안(팬 ±2.30, 틸트 0~1.571 rad). 원본은 ±2.8까지 보냈음
  - 지점마다 실제 도착 여부·시간·오차 확인 (/run/onvif_srvd/live = 1초마다 MCU 실측 각도)
  - 시험 중 새로 생긴 PTZ-ALERT(모터 꺼짐 등) 확인
  - 끝나거나 Ctrl+C로 멈추면 시작 위치로 되돌림, 결과 요약 + CSV 저장

  (PC에서)   ssh ptz@<장비IP>
  (장비에서) python3 ~/workspace/onvif_setup/onvif_pan_tilt.py            # 전체 (틸트 15단계, 편도)
             python3 ~/workspace/onvif_setup/onvif_pan_tilt.py --quick    # 틸트 3단계
             python3 ~/workspace/onvif_setup/onvif_pan_tilt.py --video    # 카메라 화면을 PC 브라우저로 같이 보기
  옵션: --speed 1.0(0.1~1)  --cycles N  --tilt-step 0.2  --port 8090(--video 화면 포트)
"""
import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request

# --help 출력은 터미널 인코딩에 상관없이 보이도록 ASCII
HELP = """Pan/tilt sweep test through ONVIF (no need to stop onvif_srvd, no R/S).
Zigzag: one pan pass per tilt level. Checks arrival/error/time per point, new PTZ-ALERTs,
returns to the start position, writes logs/*.csv.
  python3 onvif_pan_tilt.py --quick          # 3 tilt levels (~25 s)
  python3 onvif_pan_tilt.py                  # full (~2 min)
  python3 onvif_pan_tilt.py --quick --video  # with camera view at http://<device-ip>:8090"""

PROFILE = "MainStream"
ONVIF_URL = "http://127.0.0.1:1000/onvif/ptz_service"
LIVE_PATH = "/run/onvif_srvd/live"
STATUS_PATH = "/tmp/onvif_pan_tilt.status"      # onvif_cam_view.py 화면에 진행 상황 표시용
PAN_LIMIT = 2.30          # 펌웨어 한계 ±2.356 안쪽
TILT_MIN, TILT_MAX = 0.0, math.pi / 2
ARRIVE_TOL = 0.03         # rad (≈1.7°) 이내면 도착(OK)
NEAR_TOL = 0.07           # 시간 초과 때 이 안이면 NEAR (≈4°, 틸트 위쪽 끝은 무게·마찰로 마지막 몇 도가 늦음)
ARRIVE_TIMEOUT = 15.0     # 지점당 최대 대기
HERE = os.path.dirname(os.path.abspath(__file__))


def wrap(x):
    return math.remainder(x, 2 * math.pi)


# ---------------------------------------------------------------- ONVIF (장비 안 127.0.0.1)
def soap(body, timeout=3):
    env = ('<?xml version="1.0" encoding="utf-8"?>'
           '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
           ' xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
           f'<s:Body>{body}</s:Body></s:Envelope>')
    req = urllib.request.Request(ONVIF_URL, data=env.encode(),
                                 headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


SPEED = None   # 0~1 (ONVIF Speed). None이면 기본 속도(팬 1.6 rad/s). 1.0 = 팬 3.0 / 틸트 1.5 rad/s


def absolute_move(pan, tilt, speed=None):
    sp = speed if speed is not None else SPEED
    spd = f'<tptz:Speed><tt:PanTilt x="{sp:.2f}" y="{sp:.2f}"/></tptz:Speed>' if sp else ""
    soap(f'<tptz:AbsoluteMove><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken>'
         f'<tptz:Position><tt:PanTilt x="{pan:.4f}" y="{tilt:.4f}"/></tptz:Position>{spd}</tptz:AbsoluteMove>')


def get_position():
    r = soap(f'<tptz:GetStatus><tptz:ProfileToken>{PROFILE}</tptz:ProfileToken></tptz:GetStatus>')
    m = re.search(r'<tt:PanTilt[^>]*x="([-\d.eE]+)"[^>]*y="([-\d.eE]+)"', r)
    if not m:
        raise RuntimeError("GetStatus: no PanTilt in reply")
    return float(m.group(1)), float(m.group(2))


# ---------------------------------------------------------------- 실측 각도
LIVE_RE = re.compile(r"^(pan|tilt)\s+current\s+([-\d.]+) rad.*?target\s+([-\d.]+) rad.*offset\s+([-\d.]+)\s+(.*)$")


def read_live():
    try:
        with open(LIVE_PATH, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return None
    d = {}
    for l in txt.splitlines():
        m = LIVE_RE.match(l)
        if m:
            d[m.group(1)] = (float(m.group(2)), float(m.group(3)), m.group(5).strip())
        elif l.split() and l.split()[0] in ("pan", "tilt") and "no reply" in l:
            d[l.split()[0]] = (float("nan"), float("nan"), "no reply")
    return d if "pan" in d and "tilt" in d else None


def alert_count():
    try:
        out = subprocess.run(["journalctl", "-u", "onvif_srvd", "-b", "--no-pager", "-q"],
                             capture_output=True, text=True, timeout=20).stdout
        return out.count("PTZ-ALERT")
    except Exception:
        return -1


# ---------------------------------------------------------------- 패턴 (pantilt.py와 같은 순서)
def build_waypoints(tilt_step, quick):
    if quick:
        tilts = [TILT_MAX, TILT_MAX / 2, TILT_MIN]
    else:
        down, t = [], TILT_MAX
        while t >= TILT_MIN - 1e-9:
            down.append(round(t, 4)); t -= tilt_step
        if down[-1] > TILT_MIN + 1e-6:
            down.append(TILT_MIN)
        tilts = down + down[-2::-1]          # 내려갔다가 다시 올라옴
    # 편도 스윕: 틸트 단계마다 팬을 한 번만 가로지르고, 끝에서 틸트만 바꿔 반대 방향으로 (지그재그)
    wps = [(-PAN_LIMIT, tilts[0])]
    for i, t in enumerate(tilts):
        end = PAN_LIMIT if i % 2 == 0 else -PAN_LIMIT
        if i > 0:
            wps.append((wps[-1][0], t))      # 팬 끝에서 틸트만 이동
        wps.append((end, t))                 # 팬 편도
    return wps


class Sweep:
    def __init__(self, a):
        self.a = a
        self.rows = []
        self.stop = False
        self.start_pos = None
        self.alerts_before = 0
        self.total = 0
        self.t0 = time.time()
        self.summary = ""

    def publish(self, phase, line=""):
        try:
            tmp = STATUS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"ts": time.time(), "phase": phase, "done": len(self.rows), "total": self.total,
                           "line": line, "summary": self.summary}, f)
            os.replace(tmp, STATUS_PATH)
        except OSError:
            pass

    def precheck(self):
        live = read_live()
        if live is None:
            raise RuntimeError(f"{LIVE_PATH} missing - check onvif_srvd (mk3-basic) is running and motors are armed")
        for ax in ("pan", "tilt"):
            if live[ax][2] != "normal":
                raise RuntimeError(f"{ax} state is '{live[ax][2]}' - test runs only when both are 'normal'")
        self.start_pos = get_position()
        self.alerts_before = alert_count()
        print(f"start position (ONVIF): pan {self.start_pos[0]:.3f}  tilt {self.start_pos[1]:.3f}")
        print(f"live: pan {live['pan'][0]:.3f}  tilt {live['tilt'][0]:.3f}  (both normal)")

    def wait_arrive(self, pan, tilt):
        t0 = time.time()
        live, first_ok = None, None
        while time.time() - t0 < ARRIVE_TIMEOUT and not self.stop:
            time.sleep(0.15)
            live = read_live()
            if not live:
                continue
            ep = abs(wrap(live["pan"][0] - pan))
            et = abs(live["tilt"][0] - tilt)
            self.publish("running", f"pan {live['pan'][0]:+.3f} -> {pan:+.3f}   tilt {live['tilt'][0]:.3f} -> {tilt:.3f}"
                                    f"   [{live['pan'][2]}/{live['tilt'][2]}]")
            if live["pan"][2] != "normal" or live["tilt"][2] != "normal":
                return False, time.time() - t0, live
            if ep < ARRIVE_TOL and et < ARRIVE_TOL:
                first_ok = first_ok or time.time()
                if time.time() - first_ok >= 0.45:   # live는 0.5초마다 갱신 → 한 번 더 확인된 뒤 도착
                    return True, time.time() - t0, live
            else:
                first_ok = None
        return False, time.time() - t0, live

    def run(self):
        wps = build_waypoints(self.a.tilt_step, self.a.quick)
        self.total = len(wps) * self.a.cycles
        self.t0 = time.time()
        n = 0
        for cyc in range(1, self.a.cycles + 1):
            for pan, tilt in wps:
                if self.stop:
                    return
                n += 1
                absolute_move(pan, tilt)
                ok, dt, live = self.wait_arrive(pan, tilt)
                cp = live["pan"][0] if live else float("nan")
                ct = live["tilt"][0] if live else float("nan")
                st = f"{live['pan'][2]}/{live['tilt'][2]}" if live else "no live data"
                row = dict(no=n, cycle=cyc, cmd_pan=pan, cmd_tilt=tilt, cur_pan=cp, cur_tilt=ct,
                           err_pan_deg=round(math.degrees(abs(wrap(cp - pan))), 2) if live else float("nan"),
                           err_tilt_deg=round(math.degrees(abs(ct - tilt)), 2) if live else float("nan"),
                           sec=round(dt, 1), result="OK" if ok else ("STOP" if self.stop else "FAIL"), state=st)
                if row["result"] == "FAIL" and live and st == "normal/normal" and \
                        math.radians(max(row["err_pan_deg"], row["err_tilt_deg"])) < NEAR_TOL:
                    row["result"] = "NEAR"
                self.rows.append(row)
                el = time.time() - self.t0
                print(f"[{n:3d}/{self.total}] cmd pan {pan:+.2f} tilt {tilt:.2f} -> cur pan {cp:+.3f} tilt {ct:.3f}"
                      f"  err {row['err_pan_deg']:.2f}/{row['err_tilt_deg']:.2f} deg  {dt:4.1f}s  {row['result']:4s}"
                      f"  {st}   (elapsed {el / 60:.1f} min)", flush=True)
                if not ok and not self.stop and st != "normal/normal":
                    print("!! motor state not normal - stopping sweep (no retry)")
                    return

    def finish(self):
        elapsed = time.time() - self.t0
        if self.start_pos:
            print(f"returning to start position pan {self.start_pos[0]:.3f} tilt {self.start_pos[1]:.3f} ...")
            try:
                absolute_move(*self.start_pos, speed=0)
                self.stop = False
                self.wait_arrive(*self.start_pos)
            except Exception as e:
                print("return failed:", e)
        alerts = alert_count() - self.alerts_before if self.alerts_before >= 0 else -1
        cnt = {k: sum(1 for r in self.rows if r["result"] == k) for k in ("OK", "NEAR", "FAIL", "STOP")}
        good = [r for r in self.rows if r["result"] in ("OK", "NEAR")]
        lines = [f"points        : {len(self.rows)}/{self.total}  OK {cnt['OK']}  NEAR {cnt['NEAR']}  "
                 f"FAIL {cnt['FAIL']}  STOP {cnt['STOP']}",
                 f"elapsed       : {elapsed / 60:.1f} min ({elapsed:.0f} s)"]
        if good:
            ep = [r["err_pan_deg"] for r in good]; et = [r["err_tilt_deg"] for r in good]; sc = [r["sec"] for r in good]
            lines += [f"error pan     : max {max(ep):.2f} deg  avg {sum(ep) / len(ep):.2f} deg",
                      f"error tilt    : max {max(et):.2f} deg  avg {sum(et) / len(et):.2f} deg",
                      f"move time     : max {max(sc):.1f} s  avg {sum(sc) / len(sc):.1f} s"]
        lines.append(f"new PTZ-ALERT : {alerts if alerts >= 0 else 'unknown (cannot read journal)'}")
        verdict = cnt["FAIL"] == 0 and cnt["STOP"] == 0 and alerts == 0 and len(self.rows) == self.total
        lines.append(f"VERDICT       : {'PASS' if verdict else 'CHECK'}")
        if self.rows:
            fn = os.path.join(self.a.out, time.strftime("onvif_pan_tilt_%Y%m%d_%H%M%S.csv"))
            with open(fn, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
                w.writeheader(); w.writerows(self.rows)
            lines.append(f"log           : {fn}")
        self.summary = "\n".join(lines)
        print("\n== PTZ pan/tilt result ==\n  " + self.summary.replace("\n", "\n  "))
        self.publish("finished - " + ("PASS" if verdict else "CHECK"))
        return verdict


def main():
    ap = argparse.ArgumentParser(description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--tilt-step", type=float, default=0.2, help="tilt step in rad (default 0.2, same as pantilt.py)")
    ap.add_argument("--quick", action="store_true", help="only 3 tilt levels (90/45/0 deg)")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="0.1-1.0 (1.0 = pan 3.0 / tilt 1.5 rad/s, firmware max). 0 = ONVIF default speed (pan 1.6)")
    ap.add_argument("--video", action="store_true", help="also start the camera view (PC browser http://<device-ip>:8090)")
    ap.add_argument("--port", type=int, default=8090, help="camera view port for --video")
    ap.add_argument("--out", default=os.path.join(HERE, "logs"), help="CSV log folder")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    # 7일 지난 결과 CSV 는 자동 삭제
    for fn in os.listdir(a.out):
        p = os.path.join(a.out, fn)
        if fn.startswith("onvif_pan_tilt_") and fn.endswith(".csv") and time.time() - os.path.getmtime(p) > 7 * 86400:
            try:
                os.remove(p)
            except OSError:
                pass
    global SPEED
    SPEED = max(0.1, min(1.0, a.speed)) if a.speed > 0 else None

    sw = Sweep(a)
    try:
        sw.precheck()
    except Exception as e:
        print("PRECHECK FAIL:", e)
        sys.exit(2)

    srv = None
    if a.video:
        sys.path.insert(0, HERE)
        import onvif_cam_view as view
        try:
            srv = view.start(a.port)
        except OSError as e:
            print(f"[WARN] camera view not started ({e}) - continuing without it (onvif_cam_view.py already running?)")
        else:
            print("waiting 5 s for the camera view ...")
            time.sleep(5)

    try:
        sw.run()
    except KeyboardInterrupt:
        print("\nCtrl+C - stopping")
        sw.stop = True
    verdict = sw.finish()

    if srv:
        print("\nCamera view still running - Ctrl+C to quit")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        view.stop(srv)
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
