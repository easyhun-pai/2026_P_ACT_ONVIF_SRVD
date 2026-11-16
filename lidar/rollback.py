"""라이다 edge 설치 되돌리기 -> 제작사 출고 상태 (PC 에서).
  python lidar_edge_rollback.py <IP> [--dry-run]
설치 전 스냅샷(data/lidar_edge/<host>_pre_*/, deploy_bundle.py 가 받음)과 비교해 edge 가 더한 것만 지운다:
서비스·유닛 파일, /home/poe/edge 등 파일, 새로 깔린 apt 패키지, 새 pip(user) 패키지.
그 뒤 스냅샷의 /etc 를 되돌린 것과 비교해 남은 차이를 보여 준다. 끝나면 재부팅.
"""
import glob, os, sys, paramiko
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("LIDAR_DATA", os.path.join(os.getcwd(), "data"))   # 결과·스냅샷 (git 에 안 올림)
USER, PW = os.environ.get("LIDAR_USER", "poe"), os.environ.get("LIDAR_PASS", "")
ip = sys.argv[1]; dry = "--dry-run" in sys.argv
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(ip, username=USER, password=PW, timeout=10)
S = f"echo '{PW}' | sudo -S -p '' "
def sh(x, t=300):
    _, o, e = c.exec_command(x, timeout=t); return (o.read() + e.read()).decode("utf-8", "replace")
host = sh("hostname").strip()
pre = sorted(glob.glob(os.path.join(DATA, "lidar_edge", f"{host}_pre_*")))[0]   # 가장 처음 스냅샷 = 출고 상태
print("snapshot", pre)
pre_pk = {l.split()[0] for l in open(os.path.join(pre, "dpkg_selections.txt"), encoding="utf-8") if l.strip().endswith("install")}
now_pk = {l.split()[0] for l in sh("dpkg --get-selections").splitlines() if l.strip().endswith("install")}
new_pk = sorted(now_pk - pre_pk)
pre_pip = {l.split()[0].lower() for l in open(os.path.join(pre, "pip_user.txt"), encoding="utf-8").read().splitlines()[2:] if l.strip()}
now_pip = {l.split()[0].lower() for l in sh("pip3 list --user 2>/dev/null").splitlines()[2:] if l.strip()}
new_pip = sorted(now_pip - pre_pip)
SVC = "edge-device-id mediamtx edge-settings edge-ptz edge-healthcheck edge-whep-bridge onvif_srvd wsdd wide-watchdog edge-splash usb-lan-names"
FILES = ("/home/poe/edge /home/poe/edge_pkg /home/poe/models /home/poe/site_check.sh /home/poe/wide_detection_fixed.sh /home/poe/onvif_srvd "
         "/home/poe/onvif_srvd.old /home/poe/onvif_srvd.pid /home/poe/edge-preinstall-*.tgz /home/poe/.edge-secrets /opt/mediamtx "
         "/usr/local/bin/onvif_srvd /usr/local/bin/wsdd /usr/local/bin/mediamtx /usr/local/lib/libgsoap* "
         "/etc/NetworkManager/dispatcher.d/90-onvif-restart /lib/dhcpcd/dhcpcd-hooks/90-onvif-restart /etc/systemd/journald.conf.d/pact-edge.conf "
         "/etc/pact-model /var/lib/onvif_srvd /run/onvif_srvd /run/onvif_srvd.ip /etc/sudoers.d/99-edge-install /opt/pact-kiosk /etc/pact-kiosk")
mosq_owned = sh("dpkg -S /lib/aarch64-linux-gnu/libmosquitto.so.1 2>/dev/null").strip()
print("new apt:", new_pk); print("new pip:", new_pip); print("libmosquitto owned by pkg:", mosq_owned or "no (edge 번들 -> 지움)")
script = f"""set -x
for s in {SVC}; do systemctl disable --now $s 2>/dev/null; rm -f /etc/systemd/system/$s.service; done
rm -rf {FILES}
{'' if mosq_owned else 'rm -f /lib/aarch64-linux-gnu/libmosquitto.so.1'}
{('DEBIAN_FRONTEND=noninteractive apt-get purge -y ' + ' '.join(new_pk)) if new_pk else 'true'}
{('sudo -u poe pip3 uninstall -y --break-system-packages ' + ' '.join(new_pip)) if new_pip else 'true'}
systemctl daemon-reload; ldconfig; systemctl restart systemd-journald
"""
print(script)
if dry: sys.exit(0)
sf = c.open_sftp(); sf.putfo(__import__("io").BytesIO(script.encode()), "/tmp/rollback.sh")
print(sh(S + "bash /tmp/rollback.sh 2>&1", 900)[-3000:])
print("LEFT:", sh("ls -d /home/poe/edge /opt/mediamtx /usr/local/bin/onvif_srvd 2>&1; systemctl list-unit-files | grep -E 'edge|onvif|wsdd|mediamtx'"))
print("재부팅:", sh(S + "sh -c 'nohup sh -c \"sleep 2; reboot\" >/dev/null 2>&1 &'"))
