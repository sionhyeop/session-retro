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
    try:
        access = input("access_token: ").strip()
        refresh = input("refresh_token: ").strip()
    except (EOFError, KeyboardInterrupt):
        # Claude Code의 `!` 실행처럼 대화형 stdin이 없는 환경에서 실행된 경우
        print("\n에러: 이 환경에서는 붙여넣기 입력을 받을 수 없습니다.", file=sys.stderr)
        print("일반 터미널(WSL 창)을 열고 아래를 실행하세요:", file=sys.stderr)
        print(f'  python3 "{Path(__file__).resolve()}" setup', file=sys.stderr)
        return 2
    if not access or not refresh:
        print("에러: 두 토큰 모두 필요합니다", file=sys.stderr)
        return 2
    save_tokens({"access_token": access, "refresh_token": refresh})
    print(f"저장됨: {TOKEN_PATH} (0600)")
    return 0


# 2026-07-28 stoneHee99/velog-mcp src/velog-client.ts에서 확인한 실제 동작 형태.
# input의 meta: {} 는 필수, url_slug는 ""이면 velog가 제목으로 자동 생성.
WRITE_POST_MUTATION = """
mutation WritePost($input: WritePostInput!) {
  writePost(input: $input) {
    id
    url_slug
    user {
      id
      username
    }
  }
}
""".strip()


def parse_frontmatter(md_text):
    """단순 YAML frontmatter 파서(외부 의존 없이 title/tags/thumbnail만 지원)."""
    meta = {}
    body = md_text
    m = re.match(r"^---\n(.*?)\n---\n?", md_text, re.DOTALL)
    if m:
        body = md_text[m.end():]
        for line in m.group(1).splitlines():
            kv = re.match(r"^(\w+):\s*(.*)$", line.strip())
            if not kv:
                continue
            key, value = kv.group(1), kv.group(2).strip()
            if not value:
                continue
            if value.startswith("[") and value.endswith("]"):
                meta[key] = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
            else:
                meta[key] = value.strip("'\"")
    return meta, body.lstrip("\n")


def write_post_draft(title, body, tags, thumbnail, tokens):
    payload = {
        "operationName": "WritePost",
        "query": WRITE_POST_MUTATION,
        "variables": {"input": {
            "title": title, "body": body, "tags": tags,
            "is_markdown": True, "is_temp": True, "is_private": False,
            "url_slug": "", "meta": {}, "thumbnail": thumbnail,
            "series_id": None, "token": None,
        }},
    }
    status, resp_headers, resp_body = _http(
        GRAPHQL_URL, method="POST",
        headers={"Content-Type": "application/json", "Cookie": cookie_header(tokens)},
        data=json.dumps(payload).encode(),
    )
    rotate_tokens(resp_headers, tokens)
    if status in (401, 403):
        raise VelogError(f"인증 실패({status}) — 토큰 만료 가능성. setup을 다시 실행하세요.")
    try:
        parsed = json.loads(resp_body)
    except json.JSONDecodeError:
        raise VelogError(f"GraphQL 응답 해석 실패(HTTP {status})")
    if status != 200 or parsed.get("errors"):
        msg = (parsed.get("errors") or [{}])[0].get("message", f"HTTP {status}")
        raise VelogError(f"WritePost 실패: {msg}")
    return parsed["data"]["writePost"]


def cmd_publish(md_path, draft=True):
    path = Path(md_path)
    if not path.is_file():
        print(f"에러: MD 파일 없음 — {path}", file=sys.stderr)
        return 5
    tokens = load_tokens()
    if not tokens or not tokens.get("access_token"):
        print("에러: 토큰 없음. 먼저 setup을 실행하세요.", file=sys.stderr)
        return 2
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    title = meta.get("title")
    if not title:
        print("에러: frontmatter에 title이 필요합니다.", file=sys.stderr)
        return 5
    try:
        new_body, n = rewrite_images(body, path.parent, tokens)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 3
    published = path.with_suffix(".published.md")
    published.write_text(f"---\ntitle: {title}\n---\n\n{new_body}", encoding="utf-8")
    print(f"이미지 {n}개 업로드, 치환본 저장: {published}")
    try:
        result = write_post_draft(title, new_body, meta.get("tags", []), meta.get("thumbnail"), tokens)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 4
    print("임시저장(초안) 업로드 완료 ✅")
    print("- 확인: https://velog.io/saves")
    print(f"- 편집: https://velog.io/write?id={result['id']}")
    print("- 공개 발행은 velog에서 직접 눌러주세요.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["setup"]:
        return cmd_setup()
    if argv[:1] == ["publish"] and len(argv) >= 2:
        return cmd_publish(argv[1], draft="--draft" in argv)
    print("사용법: velog_publish.py setup | publish <md파일> --draft", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
