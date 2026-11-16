"""묶음(edge_v1.0.1-lidar.zip)으로 라이다에 설치 (PC 에서).  python deploy_bundle.py <IP> [--zip build/edge_v1.0.1-lidar.zip] [--no-snapshot]
계정·비밀번호: 환경변수 LIDAR_USER / LIDAR_PASS (비밀번호는 LIDAR_PASS 필수)
처음 설치면 설치 전 스냅샷(롤백용)을 먼저 받는다. 설치 동안만 poe sudo 비밀번호 생략, 끝나면 지우고 재부팅."""
import os, sys, time, subprocess, paramiko
HERE = os.path.dirname(os.path.abspath(__file__)); ip = sys.argv[1]
DATA = os.environ.get("LIDAR_DATA", os.path.join(os.getcwd(), "data"))   # 결과·스냅샷 (git 에 안 올림)
ZIP = sys.argv[sys.argv.index("--zip") + 1] if "--zip" in sys.argv else os.path.join(os.getcwd(), "build", "edge_v1.0.1-lidar.zip")
USER, PW = os.environ.get("LIDAR_USER", "poe"), os.environ.get("LIDAR_PASS", "")
S = f"echo '{PW}' | sudo -S -p '' "
def conn():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy()); c.connect(ip, username=USER, password=PW, timeout=10); return c
c = conn()
def sh(x, t=120):
    _, o, e = c.exec_command(x, timeout=t); return (o.read() + e.read()).decode("utf-8", "replace")
host = sh("hostname").strip()
first = "edge" not in sh("ls ~")
if first and "--no-snapshot" not in sys.argv:
    D = os.path.join(DATA, "lidar_edge", f"{host}_pre_{time.strftime('%Y%m%d_%H%M')}"); os.makedirs(D, exist_ok=True)
    for n, cmd in (("dpkg_selections.txt", "dpkg --get-selections"), ("enabled_units.txt", "systemctl list-unit-files --no-legend"),
                   ("pip_user.txt", "pip3 list --user 2>/dev/null"), ("nm_connections.txt", "nmcli -t con show"), ("ip.txt", "ip -br a; ip r")):
        open(os.path.join(D, n), "w", encoding="utf-8").write(sh(cmd))
    _, o, _ = c.exec_command(S + "tar --numeric-owner --xattrs -cpzf - /etc /home/poe /usr/local /opt 2>/dev/null", timeout=900)
    with open(os.path.join(D, "pre_etc_home_usrlocal_opt.tar.gz"), "wb") as f:
        for b in iter(lambda: o.read(1 << 20), b""): f.write(b)
    print("snapshot", D, flush=True)
print(host, "first install" if first else "upgrade", flush=True)
c.open_sftp().put(ZIP, "/home/poe/edge_v1.0.1-lidar.zip")
sh("cd ~ && rm -rf edge_v1.0.1-lidar && python3 -m zipfile -e edge_v1.0.1-lidar.zip . && rm -f edge_v1.0.1-lidar.zip")
sh(S + "sh -c \"echo 'poe ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/99-edge-install && chmod 440 /etc/sudoers.d/99-edge-install\"")
_, o, _ = c.exec_command("cd ~/edge_v1.0.1-lidar && setsid nohup bash install_lidar.sh </dev/null >/tmp/install_lidar.log 2>&1 & echo started", timeout=20); o.read()
t = time.time()
while time.time() - t < 1500:
    time.sleep(10)
    try:
        if sh("pgrep -f '^bash install_lidar.sh' >/dev/null && echo RUN || echo DONE").strip() == "DONE": break
    except Exception:
        time.sleep(5); c = conn()
lg = sh("sed 's/\x1b\[[0-9;]*m//g' /tmp/install_lidar.log")
sh(S + "rm -f /etc/sudoers.d/99-edge-install")
print("\n".join(l for l in lg.splitlines() if "[INFO]" in l or "[WARN]" in l or "[ERROR]" in l))
ok = "설치 완료" in lg
print("INSTALL", "OK" if ok else "FAIL")
if ok:
    sh(S + "sh -c 'nohup sh -c \"sleep 2; reboot\" >/dev/null 2>&1 &'"); print("reboot sent")
