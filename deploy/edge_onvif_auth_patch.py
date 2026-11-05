#!/usr/bin/env python3
"""edge settings_handler.py 에 ONVIF 비밀번호 원문 파일 쓰기 추가 (onvif_srvd 2단계 계정 확인용).

  sudo python3 edge_onvif_auth_patch.py /home/ptz/edge/settings_handler.py      # 고친 파일을 그 자리에 씀 (이미 고쳤으면 그대로)

- 비밀번호 변경: /var/lib/onvif_srvd/onvif_auth 에 원문 (root 600, 임시 파일 → rename)
- 초기화: 파일 삭제 (onvif 는 시리얼로 확인)
- 실패해도 웹 비밀번호 변경은 그대로 진행 (경고 로그만)
"""
import sys

p = sys.argv[1]
t = open(p, encoding="utf-8").read()
if "ONVIF_AUTH_FILE" in t:
    print("already patched")
    sys.exit(0)

HELPER = '''

ONVIF_AUTH_FILE = "/var/lib/onvif_srvd/onvif_auth"


def _write_onvif_password(password: str | None):
    """ONVIF(onvif_srvd) 계정 확인용 비밀번호 원문 — root 만 읽기(600). None 이면 지운다 (초기화 → 시리얼).

    ODM·NVR 은 비밀번호를 PasswordDigest(SHA1(nonce+created+원문))로 보내 해시만으로는 확인할 수 없다.
    onvif_srvd 는 이 원문이 .device_auth 의 해시와 맞을 때만 쓴다 (옛 값이 남아도 안전).
    """
    try:
        if password is None:
            if os.path.exists(ONVIF_AUTH_FILE):
                os.remove(ONVIF_AUTH_FILE)
            return
        os.makedirs(os.path.dirname(ONVIF_AUTH_FILE), exist_ok=True)
        tmp = ONVIF_AUTH_FILE + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(password)
        os.chmod(tmp, 0o600)
        os.replace(tmp, ONVIF_AUTH_FILE)
    except Exception as e:  # noqa: BLE001 — ONVIF 쪽 실패로 웹 비밀번호 변경을 막지 않는다
        logger.warning("[ONVIF 인증] 비밀번호 파일 저장 실패: %s", e)
'''

anchor = "\ndef _verify_password(password: str) -> bool:"
assert t.count(anchor) == 1, "anchor _verify_password"
t = t.replace(anchor, HELPER + "\n" + anchor, 1)

o1 = '            _set_password_hash(_hash_pw(new_pw), "변경")\n'
assert t.count(o1) == 1, "change call"
t = t.replace(o1, o1 + '            _write_onvif_password(new_pw)\n', 1)

o2 = '            _set_password_hash(None, "초기화")\n'
assert t.count(o2) == 1, "reset call"
t = t.replace(o2, o2 + '            _write_onvif_password(None)\n', 1)

open(p, "w", encoding="utf-8").write(t)
print("patched")
