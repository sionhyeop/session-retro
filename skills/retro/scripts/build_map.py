#!/usr/bin/env python3
"""콘텐츠 맵 생성기: retro/의 실데이터로 에피소드 진행 상황 지도를 그린다.

단계: planned(계획) → spec(스펙) → draft(초안·임시저장) → published_private → published_public.
데이터: specs/*.md frontmatter·본문, out/blog/*.md + *.velog.json 사이드카, out/ppt/*.html,
overview.md 에피소드 목차(방어적 파싱), assets/ 파일 수.
단일 파일 HTML(외부 요청 0). 표준 라이브러리만, AI 호출 없음.
"""
import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

STAGES = ["planned", "spec", "draft", "published_private", "published_public"]
STAGE_LABEL = {
    "planned": ("⚪", "계획"), "spec": ("🔵", "스펙 작성됨"), "draft": ("🟡", "초안 있음"),
    "published_private": ("🟣", "비공개 발행"), "published_public": ("🟢", "공개 발행"),
}
SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")


def _frontmatter(text):
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    body = text[m.end():] if m else text
    if m:
        for line in m.group(1).splitlines():
            kv = re.match(r"^(\w+):\s*(.*)$", line.strip())
            if kv and kv.group(2).strip():
                meta[kv.group(1)] = kv.group(2).strip().strip("'\"")
    return meta, body


def _slug(path):
    m = SLUG_RE.match(path.stem)
    return m.group(1) if m else path.stem


def parse_spec(path):
    meta, body = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    problems, gaps, images = [], [], 0
    for section in re.split(r"\n(?=### )", body):
        head = section.splitlines()[0].strip() if section.strip() else ""
        n_img = section.count("![")
        images += n_img
        if head.startswith("### 문제"):
            name = head.lstrip("# ").strip()
            problems.append(name)
            if n_img == 0:
                gaps.append(name)
    return {
        "slug": _slug(path), "title": meta.get("title", path.stem),
        "period": meta.get("period", ""), "updated": meta.get("updated", ""),
        "problems": problems, "gaps": gaps, "images": images,
    }


def collect(retro_dir):
    retro = Path(retro_dir)
    episodes = []
    blogs = {_slug(p): p for p in (retro / "out" / "blog").glob("*.md")
             if not p.name.endswith(".published.md")}
    decks = {_slug(p) for p in (retro / "out" / "ppt").glob("*.html")}
    for spec_path in sorted((retro / "specs").glob("*.md")):
        ep = parse_spec(spec_path)
        ep.update(stage="spec", deck=ep["slug"] in decks, url="")
        blog = blogs.get(ep["slug"])
        if blog:
            ep["stage"] = "draft"
            sidecar = blog.with_suffix(".velog.json")
            if sidecar.is_file():
                try:
                    sc = json.loads(sidecar.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    sc = {}
                vis = sc.get("visibility", "")
                if vis in ("private", "public"):
                    ep["stage"] = f"published_{vis}"
                    if sc.get("username") and sc.get("url_slug"):
                        ep["url"] = f"https://velog.io/@{sc['username']}/{sc['url_slug']}"
        episodes.append(ep)
    # overview 목차의 계획 항목 (스펙 없는 것만, 방어적)
    overview = retro / "overview.md"
    if overview.is_file():
        text = overview.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^## 에피소드 목차\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
        if m:
            known_titles = {e["title"] for e in episodes}
            for line in m.group(1).splitlines():
                bullet = re.match(r"^-\s+(.+)$", line.strip())
                if not bullet:
                    continue
                name = re.split(r"\s+[—–|]\s+", bullet.group(1))[0].strip()
                if name and not any(name in t or t in name for t in known_titles):
                    episodes.append({"slug": "", "title": name, "period": "", "updated": "",
                                     "problems": [], "gaps": [], "images": 0,
                                     "stage": "planned", "deck": False, "url": ""})
    return episodes


def assets_summary(retro_dir):
    retro = Path(retro_dir)
    count = lambda d: len([p for p in (retro / "assets" / d).glob("*") if p.is_file()])  # noqa: E731
    return {"auto": count("auto"), "inbox": count("inbox")}


def next_suggestion(episodes):
    if not episodes:
        return None
    return sorted(episodes, key=lambda e: (STAGES.index(e["stage"]), e["updated"]))[0]


def render_html(episodes, assets, project_name):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    nxt = next_suggestion([e for e in episodes if e["stage"] != "published_public"] or episodes)
    cards = []
    for e in episodes:
        dot, label = STAGE_LABEL[e["stage"]]
        img = f"⚠️ 이미지 부족: {', '.join(e['gaps'])}" if e["gaps"] else \
              (f"이미지 {e['images']}장" if e["images"] else ("이미지 없음" if e["stage"] != "planned" else ""))
        badges = []
        if e["stage"].startswith("published") or e["stage"] == "draft":
            badges.append("📝 블로그")
        if e["deck"]:
            badges.append("🎞️ 덱")
        link = f'<a href="{html.escape(e["url"])}">{html.escape(e["url"])}</a>' if e["url"] else ""
        hot = ' style="outline:2px solid var(--accent)"' if nxt and e is nxt else ""
        cards.append(f"""
  <div class="card stage-{e['stage']}"{hot}>
    <div class="dot">{dot} <span>{label}</span></div>
    <h3>{html.escape(e['title'])}</h3>
    <p class="dim">{html.escape(e['period'] or '')} {'· ' + html.escape(e['updated']) if e['updated'] else ''}</p>
    <p class="dim">{html.escape(img)}</p>
    <p>{' · '.join(badges)}</p>
    <p class="dim">{link}</p>
  </div>""")
    legend = " ".join(f"{d} {l}" for d, l in STAGE_LABEL.values())
    nxt_line = f"다음 작성 추천: <b>{html.escape(nxt['title'])}</b>" if nxt else "에피소드가 없습니다 — /retro로 시작하세요"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>콘텐츠 맵 — {html.escape(project_name)}</title>
<style>
:root {{ --bg:#111418; --fg:#e8eaed; --dim:#9aa0a6; --accent:#7aa2f7; --card:#1b2027; --line:#2a313b; }}
@media (prefers-color-scheme: light) {{ :root {{ --bg:#f7f8fa; --fg:#1b2027; --dim:#5f6672; --accent:#3b6fd4; --card:#fff; --line:#dde2e9; }} }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--fg); line-height:1.6; padding:40px 24px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Pretendard","Noto Sans KR","Malgun Gothic",sans-serif; }}
main {{ max-width:960px; margin:0 auto; }}
h1 {{ font-size:32px; margin-bottom:4px; }} h3 {{ font-size:19px; margin:8px 0 4px; }}
.dim {{ color:var(--dim); font-size:14px; }}
.meta {{ margin:10px 0 24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }}
.dot span {{ color:var(--dim); font-size:13px; }}
a {{ color:var(--accent); word-break:break-all; }}
.stage-planned {{ opacity:.75; border-style:dashed; }}
</style></head><body><main>
<h1>콘텐츠 맵</h1>
<p class="dim">{html.escape(project_name)} · 생성 {now} · 범례: {legend}</p>
<p class="meta">{nxt_line} · 미배치 이미지: inbox {assets['inbox']}장 / auto {assets['auto']}장</p>
<div class="grid">{''.join(cards)}
</div>
<p class="dim" style="margin-top:28px">/retro · /retro-blog · /retro-ppt 실행 시 자동 갱신됩니다.</p>
</main></body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="retro 콘텐츠 맵 생성")
    ap.add_argument("--retro-dir", default="retro")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    retro = Path(args.retro_dir)
    if not retro.is_dir():
        print(f"에러: retro 디렉토리 없음 — {retro}", file=sys.stderr)
        return 1
    episodes = collect(retro)
    text = render_html(episodes, assets_summary(retro), retro.resolve().parent.name)
    out = Path(args.out) if args.out else retro / "map.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"작성됨: {out} (에피소드 {len(episodes)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
