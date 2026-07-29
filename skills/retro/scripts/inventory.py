#!/usr/bin/env python3
"""프로젝트 인벤토리: 세션 기록 × git 커밋 교차표 (소급 회고의 1단계).

세션별 제목·기간·턴·도구실패와 그 시간대(±30분)의 git 커밋을 마크다운 표로 만든다.
에피소드(주제 단위) 클러스터링은 이 표를 읽는 Claude가 수행한다.
표준 라이브러리만 사용. AI 호출 없음.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_transcript import parse_lines  # noqa: E402

PAD = datetime.timedelta(minutes=30)


def default_session_files():
    """현재 보관분(~/.claude/projects) + retro/archive를 세션ID로 중복 제거(원본 우선)."""
    munged = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
    proj = Path.home() / ".claude" / "projects" / munged
    files = {}
    if proj.is_dir():
        for p in sorted(proj.glob("*.jsonl")):
            files[p.stem[:8]] = p
    for p in sorted(Path("retro/archive").glob("*.jsonl")):
        m = re.match(r"\d{4}-\d{2}-\d{2}-([0-9a-f]{8})", p.name)
        files.setdefault(m.group(1) if m else p.stem, p)
    return list(files.values())


def session_row(path):
    _, stats = parse_lines(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return {
        "file": path.name,
        "title": " / ".join(stats["titles"]) or "(제목 없음)",
        "first": stats["first_ts"], "last": stats["last_ts"],
        "turns": stats["turns"], "errors": stats["errors"], "commits": [],
    }


def git_commits(repo="."):
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--format=%h%x09%aI%x09%s"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    commits = []
    for line in out.stdout.splitlines():
        try:
            h, iso, subject = line.split("\t", 2)
            commits.append({"hash": h, "ts": datetime.datetime.fromisoformat(iso), "subject": subject})
        except ValueError:
            continue
    return commits


def assign(commits, rows):
    """커밋을 세션 시간창(±30분)에 귀속시키고 미귀속 목록을 반환."""
    unassigned = []
    for c in commits:
        hit = None
        for r in rows:
            if r["first"] and r["last"] and r["first"] - PAD <= c["ts"] <= r["last"] + PAD:
                hit = r
                break
        (hit["commits"] if hit else unassigned).append(c)
    return unassigned


def render(rows, unassigned, git_available):
    lines = ["# 프로젝트 인벤토리", ""]
    lines.append(f"- 세션 {len(rows)}개" + ("" if git_available else " · git 저장소 아님(커밋 정보 없음)"))
    lines += ["", "## 세션 (시간순)", "",
              "| 날짜 | 세션 제목 | 시간 | 턴 | 도구실패 | 커밋 |", "|---|---|---|---|---|---|"]
    far_past = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    for r in sorted(rows, key=lambda r: r["first"] or far_past):
        date = f"{r['first']:%m-%d %H:%M}" if r["first"] else "?"
        dur = int((r["last"] - r["first"]).total_seconds() // 60) if r["first"] and r["last"] else 0
        commits = "<br>".join(f"`{c['hash']}` {c['subject'][:60]}" for c in r["commits"]) or "-"
        lines.append(f"| {date} | {r['title'][:40]} | {dur}분 | {r['turns']} | {r['errors']} | {commits} |")
    if unassigned:
        lines += ["", "## 세션 기록이 없는 커밋 (30일 경과로 소실됐거나 Claude 밖에서 작업)", "",
                  "| 날짜 | 커밋 | 메시지 |", "|---|---|---|"]
        for c in sorted(unassigned, key=lambda c: c["ts"]):
            lines.append(f"| {c['ts']:%m-%d} | `{c['hash']}` | {c['subject'][:70]} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="세션 × git 인벤토리")
    ap.add_argument("--sessions", nargs="*", help="세션 JSONL 경로 (기본: 자동 탐색)")
    ap.add_argument("--repo", default=".", help="git 저장소 경로")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.sessions] if args.sessions else default_session_files()
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("에러: 세션 기록이 없습니다", file=sys.stderr)
        return 1
    rows = [session_row(p) for p in paths]
    commits = git_commits(args.repo)
    unassigned = assign(commits, rows) if commits else []
    text = render(rows, unassigned, commits is not None)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"작성됨: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
