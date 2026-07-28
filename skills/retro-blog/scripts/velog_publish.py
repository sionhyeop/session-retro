#!/usr/bin/env python3
"""velog 비공식 API 업로더: 이미지 CDN 업로드 + 임시저장(초안) 업로드.

- 공식 API가 없어 velog 내부 GraphQL/REST를 사용한다. 언제든 깨질 수 있으며,
  깨지면 호출측(retro-blog 스킬)이 'MD 붙여넣기' 폴백으로 안내한다.
- 항상 is_temp(임시저장) 전용. 공개 발행은 지원하지 않는다.
- 토큰은 ~/.config/velog-retro/tokens.json(0600). 로그·에러에 절대 노출 금지.
- 표준 라이브러리만 사용.
종료 코드: 0 성공 / 2 토큰 없음·만료 / 3 이미지 업로드 실패 / 4 GraphQL 실패 / 5 MD 형식 오류
"""
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

UPLOAD_URL = "https://v3.velog.io/api/files/v3/upload"
GRAPHQL_URL = "https://v3.velog.io/graphql"
TOKEN_PATH = Path.home() / ".config" / "velog-retro" / "tokens.json"


class VelogError(Exception):
    """API 실패. 메시지에 토큰을 절대 포함하지 않는다."""


def _http(url, method="GET", headers=None, data=None):
    """유일한 네트워크 지점. (status, header_items, body) 반환. 테스트에서 monkeypatch."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, list(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, list(e.headers.items()), e.read()


def load_tokens():
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_tokens(tokens):
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(tokens), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)


def cookie_header(tokens):
    return f"access_token={tokens.get('access_token', '')}; refresh_token={tokens.get('refresh_token', '')}"


def rotate_tokens(header_items, tokens):
    """응답 Set-Cookie의 토큰 회전을 저장소에 반영."""
    changed = False
    for key, value in header_items:
        if key.lower() != "set-cookie":
            continue
        m = re.match(r"(access_token|refresh_token)=([^;]+)", value)
        if m and tokens.get(m.group(1)) != m.group(2):
            tokens[m.group(1)] = m.group(2)
            changed = True
    if changed:
        save_tokens(tokens)


def _multipart(fields, file_field, file_path):
    boundary = "----velogretro" + uuid.uuid4().hex
    chunks = []
    for key, value in fields.items():
        chunks += [f"--{boundary}".encode(),
                   f'Content-Disposition: form-data; name="{key}"'.encode(),
                   b"", str(value).encode()]
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    chunks += [f"--{boundary}".encode(),
               f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"'.encode(),
               f"Content-Type: {ctype}".encode(), b"", file_path.read_bytes()]
    chunks += [f"--{boundary}--".encode(), b""]
    return b"\r\n".join(chunks), f"multipart/form-data; boundary={boundary}"


def upload_image(path, tokens):
    body, content_type = _multipart({"type": "post"}, "image", path)
    status, resp_headers, resp_body = _http(
        UPLOAD_URL, method="POST",
        headers={"Content-Type": content_type, "Cookie": cookie_header(tokens)},
        data=body,
    )
    rotate_tokens(resp_headers, tokens)
    if status in (401, 403):
        raise VelogError(f"인증 실패({status}) — 토큰 만료 가능성. setup을 다시 실행하세요.")
    if status != 200:
        raise VelogError(f"이미지 업로드 실패({status}): {path.name}")
    try:
        return json.loads(resp_body)["path"]
    except (json.JSONDecodeError, KeyError):
        raise VelogError(f"이미지 업로드 응답 해석 실패: {path.name}")


IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def rewrite_images(md_text, md_dir, tokens):
    """MD의 로컬 이미지를 업로드하고 CDN URL로 치환. (새 MD, 업로드 수) 반환."""
    count = 0

    def repl(m):
        nonlocal count
        alt, src = m.group(1), m.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        local = (md_dir / src).resolve()
        if not local.is_file():
            print(f"경고: 이미지 없음, 건너뜀 — {src}", file=sys.stderr)
            return m.group(0)
        url = upload_image(local, tokens)
        count += 1
        print(f"업로드됨: {src} -> {url}")
        return f"![{alt}]({url})"

    return IMG_RE.sub(repl, md_text), count


def cmd_setup():
    print("velog.io 로그인 → 개발자도구(F12) → Application → Cookies → https://velog.io 에서 값 복사")
    access = input("access_token: ").strip()
    refresh = input("refresh_token: ").strip()
    if not access or not refresh:
        print("에러: 두 토큰 모두 필요합니다", file=sys.stderr)
        return 2
    save_tokens({"access_token": access, "refresh_token": refresh})
    print(f"저장됨: {TOKEN_PATH} (0600)")
    return 0


if __name__ == "__main__":
    sys.exit(cmd_setup() if len(sys.argv) > 1 and sys.argv[1] == "setup" else 1)
