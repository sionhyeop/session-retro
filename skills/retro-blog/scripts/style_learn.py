#!/usr/bin/env python3
"""말투 학습 1단계: 내 velog 공개 글을 수집해 문체 분석용 코퍼스를 만든다.

- 공개 읽기 API(v2 GraphQL)만 사용 — 인증 불필요, 본인 공개 글 대상.
- 이 스크립트는 수집·기초 통계만 한다(AI 호출 없음). 문체 프로필 증류는
  코퍼스를 읽는 Claude가 수행해 ~/.config/velog-retro/style.md 에 저장한다.
- 표준 라이브러리만 사용.
사용법: style_learn.py <username> [--max 10] [--out ~/.config/velog-retro/style-corpus.md]
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

V2_GRAPHQL = "https://v2.velog.io/graphql"
DEFAULT_OUT = Path.home() / ".config" / "velog-retro" / "style-corpus.md"
POST_CHARS = 3000  # 글당 코퍼스에 담는 최대 분량 — 문체는 앞부분에서 충분히 드러난다

POSTS_QUERY = """
query Posts($username: String!, $limit: Int) {
  posts(username: $username, limit: $limit) {
    title
    url_slug
    released_at
    is_private
  }
}
""".strip()

READ_POST_QUERY = """
query ReadPost($username: String!, $url_slug: String!) {
  post(username: $username, url_slug: $url_slug) {
    title
    body
  }
}
""".strip()


def _http(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, list(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, list(e.headers.items()), e.read()


def _graphql(query, variables):
    status, _, body = _http(
        V2_GRAPHQL, method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"query": query, "variables": variables}).encode(),
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"응답 해석 실패(HTTP {status})")
    if status != 200 or parsed.get("errors"):
        msg = (parsed.get("errors") or [{}])[0].get("message", f"HTTP {status}")
        raise RuntimeError(f"조회 실패: {msg}")
    return parsed["data"]


def fetch_posts(username, limit=10):
    posts = _graphql(POSTS_QUERY, {"username": username, "limit": limit})["posts"] or []
    return [p for p in posts if not p.get("is_private")]


def fetch_body(username, url_slug):
    return _graphql(READ_POST_QUERY, {"username": username, "url_slug": url_slug})["post"]


def ending_stats(text):
    """어미·기호 사용 빈도 — 결정적 기초 통계 (해석은 Claude 몫)."""
    return {
        "습니다": len(re.findall(r"습니다[.!?]?", text)),
        "어요/아요": len(re.findall(r"[어아]요[.!?]", text)),
        "라고요/네요/거든요": len(re.findall(r"(라고|네|거든)요[.!?]", text)),
        "다.": len(re.findall(r"[^요다니]다\.", text)),  # "~습니다."는 위에서 따로 센다
        "물음표": text.count("?"),
        "느낌표": text.count("!"),
        "이모지·기호": len(re.findall(r"[😀-🙏✨🔥💡⚠️❌✅🎉]|[😺-🙀]", text)),
        "코드블록": text.count("```") // 2,
    }


def build_corpus(username, posts, max_chars=POST_CHARS):
    all_text = "\n".join(p.get("body", "") for p in posts)
    stats = ending_stats(all_text)
    lines = [f"# 문체 코퍼스: @{username} (공개 글 {len(posts)}개)", "",
             "## 문체 통계 (전체)", ""]
    lines += [f"- {k}: {v}" for k, v in stats.items()]
    for p in posts:
        body = (p.get("body") or "").strip()
        if len(body) > max_chars:
            body = body[:max_chars] + "\n…(이하 생략)"
        lines += ["", "---", "", f"## {p.get('title', '(제목 없음)')} ({p.get('released_at', '')[:10]})", "", body]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="velog 공개 글 → 문체 코퍼스")
    ap.add_argument("username")
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    try:
        posts = fetch_posts(args.username, limit=args.max)
    except RuntimeError as e:
        print(f"에러: {e}", file=sys.stderr)
        return 1
    if not posts:
        print(f"에러: @{args.username} 의 공개 글이 없습니다 — 학습할 재료가 없어요.", file=sys.stderr)
        return 1
    full = []
    for p in posts[:args.max]:
        try:
            body = fetch_body(args.username, p["url_slug"])
        except RuntimeError as e:
            print(f"경고: {p['url_slug']} 본문 조회 실패({e}), 건너뜀", file=sys.stderr)
            continue
        full.append({**p, **(body or {})})
    if not full:
        print("에러: 본문을 하나도 가져오지 못했습니다.", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_corpus(args.username, full), encoding="utf-8")
    print(f"작성됨: {out} (글 {len(full)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
