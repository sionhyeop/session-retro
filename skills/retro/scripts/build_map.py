#!/usr/bin/env python3
"""콘텐츠 맵 생성기: 프로젝트 활동 전체(세션×커밋 타임라인) 위에 에피소드 커버리지를 그린다.

"발행물 목록"이 아니라 지도다 — 영토는 프로젝트의 모든 활동일이고, 각 날이 어느
에피소드로 쓰였는지 색칠되며, 어떤 글에도 속하지 않은 날은 "미작성 구간"으로 드러난다.
단계: planned(계획) → spec(스펙) → draft(초안) → published_private → published_public.
단일 파일 HTML(외부 요청 0). 표준 라이브러리만, AI 호출 없음.
"""
import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory import assign, default_session_files, git_commits, session_row  # noqa: E402

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


def parse_period(period_str):
    """'YYYY-MM-DD ~ YYYY-MM-DD' → (date, date). 실패 시 None."""
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", period_str or "")
    if not dates:
        return None
    start = datetime.date.fromisoformat(dates[0])
    end = datetime.date.fromisoformat(dates[-1])
    return (start, end) if start <= end else (end, start)


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
        "period": meta.get("period", ""), "dates": parse_period(meta.get("period", "")),
        "updated": meta.get("updated", ""),
        "problems": problems, "gaps": gaps, "images": images,
    }


def collect(retro_dir):
    """에피소드(스펙+발행 상태) 수집 — 지도의 '쓰인 영역'."""
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
                    episodes.append({"slug": "", "title": name, "period": "", "dates": None,
                                     "updated": "", "problems": [], "gaps": [], "images": 0,
                                     "stage": "planned", "deck": False, "url": ""})
    return episodes


def parse_backlog(retro_dir):
    """retro/plan.md 콘텐츠 백로그 — AI가 미리 스케치해둔 '앞으로 쓸 것들'.

    형식: 마크다운 표 | 가제 | 훅(한 줄) | 근거 | 태그 | (우선순위 = 행 순서)"""
    plan = Path(retro_dir) / "plan.md"
    if not plan.is_file():
        return []
    items = []
    for line in plan.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("가제", ""):
            continue
        items.append({"title": cells[0], "hook": cells[1] if len(cells) > 1 else "",
                      "basis": cells[2] if len(cells) > 2 else "",
                      "tags": cells[3] if len(cells) > 3 else ""})
    return items


def collect_timeline(repo=".", session_paths=None):
    """활동일 타임라인 — 지도의 '영토'. 날짜별 {sessions, turns, errors, commits}."""
    paths = session_paths if session_paths is not None else default_session_files()
    rows = [session_row(p) for p in paths if Path(p).is_file()]
    commits = git_commits(repo) or []
    orphan_commits = assign(commits, rows)
    days = {}

    def day_of(ts):
        return ts.date() if ts else None

    for r in rows:
        d = day_of(r["first"])
        if not d:
            continue
        day = days.setdefault(d, {"date": d, "sessions": [], "turns": 0, "errors": 0, "commits": 0})
        day["sessions"].append(r["title"])
        day["turns"] += r["turns"]
        day["errors"] += r["errors"]
        day["commits"] += len(r["commits"])
    for c in orphan_commits:
        d = c["ts"].date()
        day = days.setdefault(d, {"date": d, "sessions": [], "turns": 0, "errors": 0, "commits": 0})
        day["commits"] += 1
    return [days[d] for d in sorted(days)]


def assign_days(days, episodes):
    """각 활동일을 period가 덮는 에피소드에 귀속. 미귀속 = 미작성 구간."""
    for day in days:
        day["episode"] = None
        for ep in episodes:
            if ep.get("dates") and ep["dates"][0] <= day["date"] <= ep["dates"][1]:
                day["episode"] = ep
                break
    return days


def coverage(days):
    total = len(days)
    covered = sum(1 for d in days if d["episode"])
    published = sum(1 for d in days if d["episode"] and d["episode"]["stage"].startswith("published"))
    pct = lambda n: round(100 * n / total) if total else 0  # noqa: E731
    return {"total": total, "covered": covered, "published": published,
            "covered_pct": pct(covered), "published_pct": pct(published)}


def uncovered_runs(days):
    """연속된 미작성 구간들 — 다음 글감 후보. 활동량(세션+커밋) 큰 순."""
    runs, cur = [], []
    for d in days:
        if d["episode"] is None:
            cur.append(d)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    weight = lambda run: sum(len(d["sessions"]) + d["commits"] for d in run)  # noqa: E731
    return sorted(runs, key=weight, reverse=True)


NEXT_ACTION = {
    "planned": lambda t: f"'{t}' 에피소드의 회고 스펙을 만들어줘",
    "spec": lambda t: f"'{t}' 스펙으로 velog 글 써줘",
    "draft": lambda t: f"'{t}' 초안을 발행해줘",
    "published_private": lambda t: f"'{t}' 공개로 바꿔줘",
    "published_public": lambda t: f"'{t}' 글 업데이트해줘",
}


def next_suggestion(episodes, days=None, backlog=None):
    if backlog:
        b = backlog[0]
        return {"kind": "backlog", "title": b["title"],
                "detail": f"{b['hook']} (근거: {b['basis'] or '기획'})"}
    runs = uncovered_runs(days) if days else []
    if runs:
        run = runs[0]
        titles = [t for d in run for t in d["sessions"] if t != "(제목 없음)"][:2]
        label = " / ".join(titles) or f"{run[0]['date']:%m-%d}~{run[-1]['date']:%m-%d} 활동"
        return {"kind": "uncovered", "title": label,
                "detail": f"{run[0]['date']:%m-%d}~{run[-1]['date']:%m-%d} · 세션 {sum(len(d['sessions']) for d in run)}개 — 아직 어떤 글에도 안 담김"}
    candidates = [e for e in episodes if e["stage"] != "published_public"] or episodes
    if not candidates:
        return None
    ep = sorted(candidates, key=lambda e: (STAGES.index(e["stage"]), e["updated"]))[0]
    return {"kind": "episode", "title": ep["title"],
            "detail": f"현재 {STAGE_LABEL[ep['stage']][1]} — 다음 단계로 진행"}


def render_html(episodes, days, assets, project_name, backlog=None):
    backlog = backlog or []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cov = coverage(days)
    nxt = next_suggestion(episodes, days, backlog)
    legend = " ".join(f"{d} {l}" for d, l in STAGE_LABEL.values())

    def go_btn(cmd):
        return f'<button class="go" data-cmd="{html.escape(cmd, quote=True)}">▶ 이어서</button>'

    # 타임라인 노드
    rows = []
    for d in days:
        ep = d["episode"]
        sess = ", ".join(t for t in d["sessions"] if t != "(제목 없음)")[:60] or \
               (f"세션 {len(d['sessions'])}개" if d["sessions"] else "커밋만 있는 날")
        meta = f"세션 {len(d['sessions'])} · 턴 {d['turns']} · 실패 {d['errors']} · 커밋 {d['commits']}"
        if ep:
            dot = STAGE_LABEL[ep["stage"]][0]
            tag = f'<span class="tag stage-{ep["stage"]}">{dot} {html.escape(ep["title"][:34])}</span>'
            cls = f"covered stage-{ep['stage']}"
        else:
            tag = ('<span class="tag uncovered-tag">⚪ 미작성 구간</span> '
                   + go_btn(f"{d['date']:%m-%d} 활동 구간의 회고를 써줘"))
            cls = "uncovered"
        rows.append(f"""
  <div class="node {cls}">
    <div class="when">{d['date']:%m-%d}</div>
    <div class="body"><b>{html.escape(sess)}</b><span class="dim">{meta}</span>{tag}</div>
  </div>""")
    if not rows:
        rows.append('<p class="dim">활동 기록이 없습니다 — 세션이 쌓이면 지도가 그려집니다.</p>')

    # 백로그 — 앞으로 쓸 것들 (AI가 미리 스케치한 기획)
    plan_cards = []
    for b in backlog:
        plan_cards.append(f"""
  <div class="plan-card">
    <b>⚪ {html.escape(b['title'])}</b>
    <span class="dim">{html.escape(b['hook'])}</span>
    <span class="dim">근거: {html.escape(b['basis'] or '기획')}{' · ' + html.escape(b['tags']) if b['tags'] else ''}</span>
    {go_btn(NEXT_ACTION['planned'](b['title']))}
  </div>""")

    # 에피소드 요약 스트립 (단계별 다음 액션 버튼 포함)
    chips = []
    for e in episodes:
        dot, label = STAGE_LABEL[e["stage"]][0], STAGE_LABEL[e["stage"]][1]
        gap = f" · ⚠️{len(e['gaps'])}" if e["gaps"] else ""
        link = f' <a href="{html.escape(e["url"])}">글</a>' if e["url"] else ""
        btn = go_btn(NEXT_ACTION[e["stage"]](e["title"]))
        chips.append(f'<span class="chip stage-{e["stage"]}">{dot} {html.escape(e["title"][:30])} <i>{label}{gap}</i>{link} {btn}</span>')

    nxt_html = ""
    if nxt:
        icon = {"backlog": "✍️ 다음 글감(기획)", "uncovered": "✍️ 다음 글감(미작성 구간)"}.get(nxt["kind"], "▶ 다음 단계")
        nxt_html = f'<p class="next"><b>{icon}:</b> {html.escape(nxt["title"])} <span class="dim">— {html.escape(nxt["detail"])}</span></p>'

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>콘텐츠 맵 — {html.escape(project_name)}</title>
<style>
:root {{ --bg:#111418; --fg:#e8eaed; --dim:#9aa0a6; --accent:#7aa2f7; --card:#1b2027; --line:#2a313b;
  --c-spec:#7aa2f7; --c-draft:#e0af68; --c-priv:#bb9af7; --c-pub:#9ece6a; }}
@media (prefers-color-scheme: light) {{ :root {{ --bg:#f7f8fa; --fg:#1b2027; --dim:#5f6672; --accent:#3b6fd4; --card:#fff; --line:#dde2e9; }} }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--fg); line-height:1.6; padding:40px 24px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Pretendard","Noto Sans KR","Malgun Gothic",sans-serif; }}
main {{ max-width:820px; margin:0 auto; }}
h1 {{ font-size:32px; }} h2 {{ font-size:20px; margin:30px 0 12px; color:var(--accent); }}
.dim {{ color:var(--dim); font-size:13.5px; display:block; }}
.stats {{ display:flex; gap:26px; margin:16px 0 4px; }}
.stats b {{ font-size:30px; color:var(--accent); }} .stats span {{ color:var(--dim); font-size:14px; display:block; }}
.next {{ background:var(--card); border:1px solid var(--accent); border-radius:12px; padding:12px 16px; margin:14px 0; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; }}
.chip {{ background:var(--card); border:1px solid var(--line); border-radius:999px; padding:6px 14px; font-size:14px; }}
.chip i {{ color:var(--dim); font-style:normal; font-size:12.5px; }}
a {{ color:var(--accent); }}
.flow {{ position:relative; margin-top:8px; padding-left:8px; }}
.node {{ display:flex; gap:16px; padding:10px 0 10px 8px; border-left:3px solid var(--line); }}
.node .when {{ width:52px; color:var(--dim); font-size:14px; padding-top:2px; flex-shrink:0; }}
.node .body {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 16px; flex:1; }}
.node .body b {{ font-size:15px; }}
.node.covered.stage-spec {{ border-left-color:var(--c-spec); }}
.node.covered.stage-draft {{ border-left-color:var(--c-draft); }}
.node.covered.stage-published_private {{ border-left-color:var(--c-priv); }}
.node.covered.stage-published_public {{ border-left-color:var(--c-pub); }}
.node.uncovered .body {{ border-style:dashed; opacity:.85; }}
.tag {{ display:inline-block; margin-top:6px; font-size:13px; border-radius:999px; padding:2px 12px; background:rgba(122,162,247,.12); }}
.uncovered-tag {{ background:transparent; border:1px dashed var(--line); color:var(--dim); }}
.plan-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px; }}
.plan-card {{ background:var(--card); border:1px dashed var(--line); border-radius:12px; padding:12px 16px;
  display:flex; flex-direction:column; gap:5px; font-size:14.5px; }}
.go {{ align-self:flex-start; margin-top:4px; background:transparent; border:1px solid var(--accent);
  color:var(--accent); border-radius:999px; padding:3px 14px; font-size:12.5px; cursor:pointer;
  font-family:inherit; }}
.go:hover {{ background:rgba(122,162,247,.15); }}
.chip .go {{ margin:0 0 0 6px; }}
#toast {{ position:fixed; bottom:22px; left:50%; transform:translateX(-50%); background:var(--accent);
  color:var(--bg); border-radius:999px; padding:9px 22px; font-size:14px; opacity:0; transition:opacity .25s; pointer-events:none; }}
</style></head><body><main>
<h1>콘텐츠 맵</h1>
<p class="dim">{html.escape(project_name)} · 생성 {now} · 범례: {legend} · <b>▶ 이어서</b>를 누르면 다음 작업 지시문이 복사됩니다 — Claude Code에 붙여넣으세요</p>
<div class="stats">
  <div><b>{cov['total']}</b><span>활동일</span></div>
  <div><b>{cov['covered_pct']}%</b><span>에피소드로 커버</span></div>
  <div><b>{cov['published_pct']}%</b><span>발행됨</span></div>
  <div><b>{len(backlog)}</b><span>기획 백로그</span></div>
</div>
{nxt_html}
<h2>앞으로 쓸 것들 — 기획 백로그</h2>
<div class="plan-grid">{''.join(plan_cards) or '<span class="dim">비어 있음 — "콘텐츠 기획해줘"라고 하면 AI가 넓게 스케치해 채웁니다 (retro/plan.md)</span>'}</div>
<h2>에피소드</h2>
<div class="chips">{''.join(chips) or '<span class="dim">아직 없음 — /retro로 시작</span>'}</div>
<h2>전체 흐름 — 무엇을 썼고, 무엇이 비었나</h2>
<div class="flow">{''.join(rows)}
</div>
<p class="dim" style="margin-top:26px">/retro · /retro-blog · /retro-ppt 실행 시 자동 갱신됩니다.</p>
<div id="toast">복사됨 ✓ Claude Code에 붙여넣으세요</div>
<script>
  function copyText(t) {{
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(t);
    var ta = document.createElement("textarea");
    ta.value = t; document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); document.body.removeChild(ta);
    return Promise.resolve();
  }}
  document.addEventListener("click", function (e) {{
    var btn = e.target.closest(".go");
    if (!btn) return;
    copyText(btn.dataset.cmd).then(function () {{
      var toast = document.getElementById("toast");
      toast.style.opacity = "1";
      setTimeout(function () {{ toast.style.opacity = "0"; }}, 1600);
    }});
  }});
</script>
</main></body></html>"""


def _open_browser(path):
    """맵을 기본 브라우저로 연다 (WSL→Windows 지원). 실패해도 무시 — 보조 기능."""
    import subprocess
    try:
        if Path("/mnt/c/Windows/explorer.exe").is_file():
            win = subprocess.run(["wslpath", "-w", str(path)], capture_output=True,
                                 text=True, check=True).stdout.strip()
            subprocess.Popen(["/mnt/c/Windows/explorer.exe", win])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def assets_summary(retro_dir):
    retro = Path(retro_dir)
    count = lambda d: len([p for p in (retro / "assets" / d).glob("*") if p.is_file()])  # noqa: E731
    return {"auto": count("auto"), "inbox": count("inbox")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="retro 콘텐츠 맵 생성")
    ap.add_argument("--retro-dir", default="retro")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--open", choices=["never", "auto", "always"], default="never",
                    help="auto=에피소드 상태가 바뀌었을 때만 브라우저로 열기")
    args = ap.parse_args(argv)
    retro = Path(args.retro_dir)
    if not retro.is_dir():
        print(f"에러: retro 디렉토리 없음 — {retro}", file=sys.stderr)
        return 1
    episodes = collect(retro)
    backlog = parse_backlog(retro)
    days = assign_days(collect_timeline(repo=args.repo), episodes)
    text = render_html(episodes, days, assets_summary(retro), retro.resolve().parent.name, backlog=backlog)
    out = Path(args.out) if args.out else retro / "map.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    cov = coverage(days)
    signature = "|".join(sorted(f"{e['slug'] or e['title']}:{e['stage']}" for e in episodes)) + \
        f"#cov{cov['covered']}/{cov['total']}#plan{len(backlog)}"
    state_file = retro / ".timeline" / "map-state.txt"
    prev = state_file.read_text(encoding="utf-8") if state_file.is_file() else None
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(signature, encoding="utf-8")
    changed = prev != signature

    counts = {}
    for e in episodes:
        dot = STAGE_LABEL[e["stage"]][0]
        counts[dot] = counts.get(dot, 0) + 1
    summary = " ".join(f"{d}{n}" for d, n in counts.items()) or "에피소드 없음"
    print(f"작성됨: {out} — 활동 {cov['total']}일 중 커버 {cov['covered_pct']}%·발행 {cov['published_pct']}% · 에피소드 {len(episodes)}개({summary}){' · 상태 변화 있음' if changed else ''}")

    if args.open == "always" or (args.open == "auto" and changed):
        _open_browser(out)
        print("→ 브라우저로 열었습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
