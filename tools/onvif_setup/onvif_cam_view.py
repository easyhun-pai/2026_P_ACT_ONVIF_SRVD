#!/usr/bin/env python3
"""
카메라 송출 확인 — 장비에서 실행, 화면은 PC 브라우저로 본다 (PC 설치 불필요, 인터넷 불필요)

  ssh ptz@<장비IP> 후 python3 ~/workspace/onvif_setup/onvif_cam_view.py → PC 브라우저 http://<장비IP>:8090
  (PC는 SSH와 브라우저만 있으면 됨 — Windows / Ubuntu / macOS 무관)

화면: 광각(WIDE) / 줌(ZOOM) 좌우 실시간 영상 + 카메라별 OK / NO SIGNAL
상세 상태(JSON): http://<장비IP>:8090/status

동작: 장비 안에서 ffmpeg가 mediamtx(127.0.0.1:8554)를 읽어 작은 JPEG로 바꿔 브라우저에 보낸다.
      영상 서버·ONVIF 설정은 건드리지 않는다. Ctrl+C로 종료하면 ffmpeg도 같이 종료.

옵션: --port 8090  --fps 15  --width 960
"""
import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --help 출력은 터미널 인코딩에 상관없이 보이도록 ASCII
HELP = """Camera stream check. Run on the device, view on the PC browser at http://<device-ip>:8090
Shows WIDE (my_camera) and ZOOM (detection_zoom) live with OK / NO SIGNAL. Details: /status (JSON)"""

STREAMS = [("wide", "WIDE  (my_camera)", "my_camera"), ("zoom", "ZOOM  (detection_zoom)", "detection_zoom")]
RTSP = "rtsp://127.0.0.1:8554/"
LIVE_PATH = "/run/onvif_srvd/live"
PANTILT_STATUS = "/tmp/onvif_pan_tilt.status"
NO_SIGNAL_SEC = 3.0

_stop = threading.Event()


# ---------------------------------------------------------------- ffmpeg → JPEG
class Grabber(threading.Thread):
    def __init__(self, key, label, path, fps, width):
        super().__init__(daemon=True)
        self.key, self.label, self.path = key, label, path
        self.fps, self.width = fps, width
        self.jpg = None
        self.t = 0.0
        self.seq = 0
        self.src_res = None
        self.src_fps = None
        self.reconnects = 0
        self.state = "connecting"
        self.cond = threading.Condition()
        self._times = []
        self.proc = None

    def _read_stderr(self, p):
        rx = re.compile(r"Video: (\w+).*?(\d{3,5})x(\d{3,5}).*?(?:([\d.]+) fps|([\d.]+) tbr)")
        for raw in iter(p.stderr.readline, b""):
            m = rx.search(raw.decode("utf-8", "replace"))
            if m and self.src_res is None:
                self.src_res = f"{m.group(2)}x{m.group(3)} {m.group(1)}"
                self.src_fps = m.group(4) or m.group(5)

    def run(self):
        while not _stop.is_set():
            self.src_res = self.src_fps = None
            cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-rtsp_transport", "tcp",
                   "-i", RTSP + self.path, "-an",
                   # fps 필터는 시작 시 프레임을 몰아서 복제하므로 쓰지 않고, 원본 속도로 받아 아래에서 솎는다
                   "-vf", f"scale={self.width}:-2", "-fps_mode", "passthrough", "-q:v", "6",
                   "-f", "image2pipe", "-c:v", "mjpeg", "-"]
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError:
                self.state = "ffmpeg not found"
                return
            threading.Thread(target=self._read_stderr, args=(self.proc,), daemon=True).start()
            self.state = "streaming"
            buf = b""
            fd = self.proc.stdout.fileno()
            while not _stop.is_set():
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    s = buf.find(b"\xff\xd8")
                    e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
                    if s < 0 or e < 0:
                        if s > 0:
                            buf = buf[s:]
                        break
                    jpg, buf = buf[s:e + 2], buf[e + 2:]
                    now = time.time()
                    if now - self.t < 1.0 / self.fps - 0.005:   # 화면 fps 상한
                        continue
                    with self.cond:
                        self.jpg, self.t, self.seq = jpg, now, self.seq + 1
                        self.cond.notify_all()
                    self._times = [x for x in self._times if now - x < 2.0] + [now]
            self.kill()
            if _stop.is_set():
                return
            self.reconnects += 1
            self.state = "reconnecting"
            time.sleep(2)

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=3)
            except Exception:
                pass

    def out_fps(self):
        t = self._times
        return (len(t) - 1) / max(1e-3, t[-1] - t[0]) if len(t) > 1 else 0.0

    def ok(self):
        return self.jpg is not None and time.time() - self.t < NO_SIGNAL_SEC

    def info(self):
        return {"label": self.label, "ok": self.ok(),
                "age": round(time.time() - self.t, 1) if self.t else None,
                "src": self.src_res, "src_fps": self.src_fps, "out_fps": round(self.out_fps(), 1),
                "reconnects": self.reconnects, "state": self.state}


GRABBERS = {}


def read_text(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def status_json():
    pt = read_text(PANTILT_STATUS)
    try:
        pt = json.loads(pt) if pt else None
        if pt and time.time() - pt.get("ts", 0) > 10:
            pt["stale"] = True
    except Exception:
        pt = None
    return {"time": time.strftime("%H:%M:%S"), "host": socket.gethostname(),
            "streams": {k: g.info() for k, g in GRABBERS.items()},
            "ptz_live": read_text(LIVE_PATH).strip(), "pan_tilt": pt}


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Camera View</title><style>
html,body{margin:0;height:100%;background:#000}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:4px;height:100%}
@media(max-aspect-ratio:1/1){.grid{grid-template-columns:1fr}}
.cam{position:relative;background:#000;min-height:0}
.cam img{width:100%;height:100%;object-fit:contain;display:block}
.tag{position:absolute;top:8px;left:8px;padding:4px 10px;border-radius:4px;background:rgba(0,0,0,.6);
     color:#fff;font:700 18px system-ui,sans-serif}
.st{position:absolute;top:8px;right:8px;padding:4px 10px;border-radius:4px;font:700 18px system-ui,sans-serif;color:#fff}
.ok{background:#1a8f1a}.bad{background:#c62020}
</style></head><body><div class="grid">
 <div class="cam"><img id="i_wide" src="/stream/wide"><span class="tag">WIDE</span><span class="st bad" id="s_wide">...</span></div>
 <div class="cam"><img id="i_zoom" src="/stream/zoom"><span class="tag">ZOOM</span><span class="st bad" id="s_zoom">...</span></div>
</div><script>
for (const k of ["wide","zoom"]) { const im=document.getElementById("i_"+k);
  im.onerror=()=>setTimeout(()=>{im.src="/stream/"+k+"?t="+Date.now()},2000); }
async function tick(){
  let s=null; try{ s=await (await fetch("/status")).json(); }catch(e){}
  for (const k of ["wide","zoom"]) { const el=document.getElementById("s_"+k);
    const ok=s&&s.streams[k]&&s.streams[k].ok; el.textContent=ok?"OK":"NO SIGNAL"; el.className="st "+(ok?"ok":"bad"); }
}
setInterval(tick,1000); tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        if path == "/status":
            return self._send(200, "application/json", json.dumps(status_json()).encode())
        if path.startswith("/snap/"):
            g = GRABBERS.get(path[6:].replace(".jpg", ""))
            if g and g.jpg:
                return self._send(200, "image/jpeg", g.jpg)
            return self._send(404, "text/plain", b"no frame")
        if path.startswith("/stream/"):
            g = GRABBERS.get(path[8:])
            if not g:
                return self._send(404, "text/plain", b"unknown stream")
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = -1
            try:
                while not _stop.is_set():
                    with g.cond:
                        g.cond.wait_for(lambda: g.seq != last or _stop.is_set(), timeout=5)
                        jpg, last = g.jpg, g.seq
                    if jpg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                     str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self._send(404, "text/plain", b"not found")


def host_ips():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
        return [ip for ip in out if ":" not in ip and not ip.startswith("192.168.1.")] or out
    except Exception:
        return []


def start(port=8090, fps=15, width=960, quiet=False):
    """뷰어 시작 (다른 스크립트에서 불러 쓸 수 있게). 서버 객체를 돌려준다."""
    for key, label, path in STREAMS:
        g = Grabber(key, label, path, fps, width)
        GRABBERS[key] = g
        g.start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not quiet:
        ips = host_ips()
        print(f"Camera view: http://{ips[0] if ips else '<device-ip>'}:{port}")
    return srv


def stop(srv=None):
    _stop.set()
    for g in GRABBERS.values():
        g.kill()
    if srv:
        srv.shutdown()


def main():
    ap = argparse.ArgumentParser(description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--fps", type=int, default=15, help="view fps sent to the browser (default 15)")
    ap.add_argument("--width", type=int, default=960, help="view width in px (default 960)")
    a = ap.parse_args()
    try:
        srv = start(a.port, a.fps, a.width)
    except OSError as e:
        sys.exit(f"[ERROR] port {a.port} unavailable: {e}  (use --port N)")
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGHUP, lambda *_: _stop.set())   # SSH 창을 닫아도 ffmpeg까지 정리
    print("Ctrl+C to quit\n")
    t0 = time.time()
    try:
        while not _stop.is_set():
            time.sleep(5)
            line = "  ".join(f"{g.label.split()[0]} {'OK' if g.ok() else 'NO SIGNAL'}" for g in GRABBERS.values())
            print(f"\r[{time.strftime('%H:%M:%S')}] {line}   ", end="", flush=True)
    except KeyboardInterrupt:
        pass
    print(f"\n== result ({time.time() - t0:.0f}s) ==")
    for g in GRABBERS.values():
        i = g.info()
        print(f"  {g.label:24s} {'OK  ' if i['ok'] else 'FAIL'}  source {i['src'] or '-'} @ {i['src_fps'] or '-'} fps"
              f"  reconnects {i['reconnects']}")
    stop(srv)


if __name__ == "__main__":
    main()
