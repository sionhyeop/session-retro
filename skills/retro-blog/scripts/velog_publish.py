#!/usr/bin/env python3
"""velog 비공식 API 업로더: 이미지 CDN 업로드 + 임시저장(초안) 업로드.

- 공식 API가 없어 velog 내부 GraphQL/REST를 사용한다. 언제든 깨질 수 있으며,
  깨지면 호출측(retro-blog 스킬)이 'MD 붙여넣기' 폴백으로 안내한다.
- 기본값은 **비공개 발행**(is_private=true, 본인만 보임). 공개는 --public 명시 시에만.
  --draft로 임시저장도 가능. visibility 명령으로 발행 후 공개↔비공개 전환.
- 토큰은 ~/.config/velog-retro/tokens.json(0600). 로그·에러에 절대 노출 금지.
- 표준 라이브러리만 사용.
종료 코드: 0 성공 / 2 토큰 없음·만료 / 3 이미지 업로드 실패 / 4 GraphQL 실패 / 5 MD 형식·발행기록 오류
"""
import argparse
import base64
import hashlib
import json
import mimetypes
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zlib
from pathlib import Path

UPLOAD_URL = "https://v3.velog.io/api/files/v3/upload"
GRAPHQL_URL = "https://v3.velog.io/graphql"      # 쓰기(v3)
V2_GRAPHQL = "https://v2.velog.io/graphql"       # 읽기(v2) — 시리즈 목록 등
KROKI_URL = "https://kroki.io/mermaid/png/"      # mermaid → PNG (한글 렌더링 검증됨)
UA = {"User-Agent": "session-retro/velog_publish"}
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
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # 타임아웃이 트레이스백으로 터졌던 실사고 재발 방지 — 우아한 실패로 강등
        raise VelogError(f"네트워크 오류({type(e).__name__}) — 잠시 후 다시 시도하세요")


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
    # velog 업로드 엔드포인트가 간헐적으로 5xx를 반환한다(실사고: 500/504) — 백오프 재시도
    for attempt, backoff in enumerate((2, 5, None)):
        status, resp_headers, resp_body = _http(
            UPLOAD_URL, method="POST",
            headers={"Content-Type": content_type, "Cookie": cookie_header(tokens)},
            data=body,
        )
        rotate_tokens(resp_headers, tokens)
        if status in (401, 403):
            raise VelogError(f"인증 실패({status}) — 토큰 만료 가능성. setup을 다시 실행하세요.")
        if status < 500:
            break
        if backoff is None:
            break
        print(f"경고: 업로드 {status} — {backoff}초 후 재시도({attempt + 2}/3): {path.name}", file=sys.stderr)
        time.sleep(backoff)
    if status != 200:
        raise VelogError(f"이미지 업로드 실패({status}): {path.name}")
    try:
        return json.loads(resp_body)["path"]
    except (json.JSONDecodeError, KeyError):
        raise VelogError(f"이미지 업로드 응답 해석 실패: {path.name}")


IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def rewrite_images(md_text, md_dir, tokens, cache=None):
    """MD의 로컬 이미지를 업로드하고 CDN URL로 치환. (새 MD, 업로드 수) 반환.

    cache: {로컬경로: CDN URL} — 이미 올린 이미지는 재업로드하지 않고 캐시를 갱신한다
    (update가 매번 전체 재업로드하다 서버 오류를 맞은 실사고의 재발 방지)."""
    count = 0
    cache = cache if cache is not None else {}

    def repl(m):
        nonlocal count
        alt, src = m.group(1), m.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        if src in cache:
            return f"![{alt}]({cache[src]})"
        local = (md_dir / src).resolve()
        if not local.is_file():
            print(f"경고: 이미지 없음, 건너뜀 — {src}", file=sys.stderr)
            return m.group(0)
        url = upload_image(local, tokens)
        cache[src] = url
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

EDIT_POST_MUTATION = """
mutation EditPost($input: EditPostInput!) {
  editPost(input: $input) {
    id
    url_slug
    user {
      id
      username
    }
  }
}
""".strip()


def _graphql(operation_name, query, input_dict, tokens):
    """GraphQL mutation 공통 실행기. data 딕셔너리 반환."""
    payload = {"operationName": operation_name, "query": query, "variables": {"input": input_dict}}
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
        raise VelogError(f"{operation_name} 실패: {msg}")
    return parsed["data"]


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


def write_post(title, body, tags, thumbnail, tokens, temp=False, private=True, series_id=None):
    """기본값 = 비공개 발행(is_private). temp=True면 임시저장."""
    data = _graphql("WritePost", WRITE_POST_MUTATION, {
        "title": title, "body": body, "tags": tags,
        "is_markdown": True, "is_temp": temp, "is_private": private,
        "url_slug": "", "meta": {}, "thumbnail": thumbnail,
        "series_id": series_id, "token": None,
    }, tokens)
    return data["writePost"]


def edit_post(post_id, title, body, tags, thumbnail, url_slug, tokens,
              temp=False, private=True, series_id=None):
    data = _graphql("EditPost", EDIT_POST_MUTATION, {
        "id": post_id, "title": title, "body": body, "tags": tags,
        "is_markdown": True, "is_temp": temp, "is_private": private,
        "url_slug": url_slug or "", "meta": {}, "thumbnail": thumbnail,
        "series_id": series_id, "token": None,
    }, tokens)
    return data["editPost"]


# 2026-07-29 실서버 프로브로 확정 — v2는 seriesList (레퍼런스의 userSeriesList는 낡은 스키마)
SERIES_QUERY = """
query SeriesList($username: String!) {
  seriesList(username: $username) {
    id
    name
    url_slug
    posts_count
  }
}
""".strip()


def fetch_series(username):
    """내 시리즈 목록 조회 (v2 읽기 API, 인증 불필요)."""
    status, _, body = _http(
        V2_GRAPHQL, method="POST",
        headers={"Content-Type": "application/json", **UA},
        data=json.dumps({"query": SERIES_QUERY, "variables": {"username": username}}).encode(),
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise VelogError(f"시리즈 조회 응답 해석 실패(HTTP {status})")
    if status != 200 or parsed.get("errors"):
        msg = (parsed.get("errors") or [{}])[0].get("message", f"HTTP {status}")
        raise VelogError(f"시리즈 조회 실패: {msg}")
    return parsed["data"]["seriesList"] or []


def cmd_series(username):
    try:
        series = fetch_series(username)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 4
    if not series:
        print(f"@{username} 에게 아직 시리즈가 없습니다. velog에서 만들 수 있어요.")
        return 0
    for s in series:
        print(f"{s['id']}\t{s['name']}\t(글 {s.get('posts_count', '?')}개)")
    return 0


def first_image_url(md_text):
    """본문의 첫 원격 이미지 URL — 썸네일 자동 지정용."""
    for m in IMG_RE.finditer(md_text):
        if m.group(2).startswith(("http://", "https://")):
            return m.group(2)
    return None


MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def convert_mermaid(md_text, tokens, cache=None):
    """velog는 mermaid를 렌더링하지 못한다 — kroki로 PNG를 만들어 CDN에 올리고 치환.

    변환 실패 시 코드블록을 그대로 두고 경고만 남긴다(글이 깨지지 않게).
    cache에 코드 해시별 CDN URL을 저장해 update 때 재변환·재업로드를 피한다."""
    count = 0
    cache = cache if cache is not None else {}

    def repl(m):
        nonlocal count
        code = m.group(1).strip()
        key = "mermaid:" + hashlib.sha1(code.encode()).hexdigest()[:12]
        if key in cache:
            return f"![다이어그램]({cache[key]})"
        try:
            enc = base64.urlsafe_b64encode(zlib.compress(code.encode(), 9)).decode()
            status, _, img = _http(KROKI_URL + enc, headers=dict(UA))
            if status != 200 or not img:
                raise VelogError(f"kroki HTTP {status}")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(img)
                tmp = Path(f.name)
            try:
                url = upload_image(tmp, tokens)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001 — 변환은 best-effort
            print(f"경고: mermaid 변환 실패({e}) — 코드블록 유지", file=sys.stderr)
            return m.group(0)
        cache[key] = url
        count += 1
        return f"![다이어그램]({url})"

    return MERMAID_RE.sub(repl, md_text), count


def _sidecar_path(path):
    return path.with_suffix(".velog.json")


def _post_url(username, url_slug):
    return f"https://velog.io/@{username}/{url_slug}" if username and url_slug else "https://velog.io/saves"


def cmd_publish(md_path, mode="private", series_id=None, keep_mermaid=False):
    """mode: private(기본, 비공개 발행) | public(공개 발행) | draft(임시저장)"""
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
    image_cache = {}
    try:
        new_body, n = rewrite_images(body, path.parent, tokens, cache=image_cache)
        if not keep_mermaid:
            new_body, n_mmd = convert_mermaid(new_body, tokens, cache=image_cache)
            if n_mmd:
                print(f"mermaid 다이어그램 {n_mmd}개를 이미지로 변환했습니다")
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 3
    published = path.with_suffix(".published.md")
    published.write_text(f"---\ntitle: {title}\n---\n\n{new_body}", encoding="utf-8")
    print(f"이미지 {n}개 업로드, 치환본 저장: {published}")
    thumbnail = meta.get("thumbnail") or first_image_url(new_body)
    temp, private = {"draft": (True, False), "private": (False, True), "public": (False, False)}[mode]
    try:
        result = write_post(title, new_body, meta.get("tags", []), thumbnail, tokens,
                            temp=temp, private=private, series_id=series_id)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 4
    username = (result.get("user") or {}).get("username", "")
    _sidecar_path(path).write_text(json.dumps({
        "id": result["id"], "url_slug": result.get("url_slug", ""), "username": username,
        "title": title, "tags": meta.get("tags", []), "thumbnail": thumbnail,
        "series_id": series_id, "visibility": mode, "images": image_cache,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if mode == "draft":
        print("임시저장(초안) 업로드 완료 ✅")
        print("- 확인: https://velog.io/saves")
        print(f"- 편집: https://velog.io/write?id={result['id']}")
    elif mode == "private":
        print("비공개로 발행 완료 ✅ (본인에게만 보입니다)")
        print(f"- 글 주소: {_post_url(username, result.get('url_slug'))}")
        print("- 공개로 전환: visibility 명령 (또는 Claude에게 '공개로 바꿔줘')")
    else:
        print("공개 발행 완료 ✅")
        print(f"- 글 주소: {_post_url(username, result.get('url_slug'))}")
    return 0


def cmd_visibility(md_path, public):
    """이미 발행된 글의 공개/비공개 전환. 로컬 치환본 내용으로 EditPost를 보낸다."""
    path = Path(md_path)
    sidecar_file = _sidecar_path(path)
    if not sidecar_file.is_file():
        print(f"에러: 발행 기록({sidecar_file.name})이 없습니다. 먼저 publish 하세요.", file=sys.stderr)
        return 5
    tokens = load_tokens()
    if not tokens or not tokens.get("access_token"):
        print("에러: 토큰 없음. 먼저 setup을 실행하세요.", file=sys.stderr)
        return 2
    sidecar = json.loads(sidecar_file.read_text(encoding="utf-8"))
    source = path.with_suffix(".published.md")
    if not source.is_file():
        source = path
    _, body = parse_frontmatter(source.read_text(encoding="utf-8"))
    try:
        edit_post(sidecar["id"], sidecar["title"], body, sidecar.get("tags", []),
                  sidecar.get("thumbnail"), sidecar.get("url_slug", ""), tokens,
                  temp=False, private=not public)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 4
    sidecar["visibility"] = "public" if public else "private"
    sidecar_file.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    state = "공개" if public else "비공개"
    print(f"{state}로 전환 완료 ✅")
    print(f"- 글 주소: {_post_url(sidecar.get('username', ''), sidecar.get('url_slug', ''))}")
    if not public:
        print("- 이제 본인에게만 보입니다.")
    return 0


def cmd_update(md_path, keep_mermaid=False, series_id=None):
    """발행된 글을 로컬 MD의 최신 내용으로 갱신한다(공개 상태 유지, 시리즈는 지정 시 변경)."""
    path = Path(md_path)
    sidecar_file = _sidecar_path(path)
    if not path.is_file():
        print(f"에러: MD 파일 없음 — {path}", file=sys.stderr)
        return 5
    if not sidecar_file.is_file():
        print(f"에러: 발행 기록({sidecar_file.name})이 없습니다. 먼저 publish 하세요.", file=sys.stderr)
        return 5
    tokens = load_tokens()
    if not tokens or not tokens.get("access_token"):
        print("에러: 토큰 없음. 먼저 setup을 실행하세요.", file=sys.stderr)
        return 2
    sidecar = json.loads(sidecar_file.read_text(encoding="utf-8"))
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    title = meta.get("title") or sidecar.get("title", "")
    tags = meta.get("tags") or sidecar.get("tags", [])
    image_cache = sidecar.get("images", {})
    try:
        new_body, n = rewrite_images(body, path.parent, tokens, cache=image_cache)
        if not keep_mermaid:
            new_body, _ = convert_mermaid(new_body, tokens, cache=image_cache)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 3
    path.with_suffix(".published.md").write_text(
        f"---\ntitle: {title}\n---\n\n{new_body}", encoding="utf-8")
    thumbnail = meta.get("thumbnail") or first_image_url(new_body) or sidecar.get("thumbnail")
    visibility = sidecar.get("visibility", "private")
    effective_series = series_id or sidecar.get("series_id")
    try:
        edit_post(sidecar["id"], title, new_body, tags, thumbnail,
                  sidecar.get("url_slug", ""), tokens,
                  temp=(visibility == "draft"), private=(visibility == "private"),
                  series_id=effective_series)
    except VelogError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 2 if "인증" in str(e) else 4
    sidecar.update(title=title, tags=tags, thumbnail=thumbnail,
                   series_id=effective_series, images=image_cache)
    sidecar_file.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"글 업데이트 완료 ✅ (이미지 {n}개 처리, {visibility} 상태 유지)")
    print(f"- 글 주소: {_post_url(sidecar.get('username', ''), sidecar.get('url_slug', ''))}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="velog_publish.py")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("setup")
    p = sub.add_parser("publish")
    p.add_argument("md")
    p.add_argument("--draft", action="store_true")
    p.add_argument("--private", action="store_true")
    p.add_argument("--public", action="store_true")
    p.add_argument("--series-id", default=None)
    p.add_argument("--keep-mermaid", action="store_true")
    u = sub.add_parser("update")
    u.add_argument("md")
    u.add_argument("--series-id", default=None)
    u.add_argument("--keep-mermaid", action="store_true")
    v = sub.add_parser("visibility")
    v.add_argument("md")
    v.add_argument("--public", action="store_true")
    v.add_argument("--private", action="store_true")
    s = sub.add_parser("series")
    s.add_argument("username")
    args = ap.parse_args(argv)

    if args.cmd == "setup":
        return cmd_setup()
    if args.cmd == "publish":
        mode = "private"  # 기본값: 비공개 발행 — 공개는 명시적으로만
        if args.draft:
            mode = "draft"
        if args.public:
            mode = "public"
        return cmd_publish(args.md, mode=mode, series_id=args.series_id,
                           keep_mermaid=args.keep_mermaid)
    if args.cmd == "update":
        return cmd_update(args.md, keep_mermaid=args.keep_mermaid, series_id=args.series_id)
    if args.cmd == "visibility":
        if args.public == args.private:
            print("에러: --public 또는 --private 중 하나를 지정하세요", file=sys.stderr)
            return 1
        return cmd_visibility(args.md, public=args.public)
    if args.cmd == "series":
        return cmd_series(args.username)
    ap.print_usage(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
