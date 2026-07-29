# session-retro v1.1 구현 계획 — 에피소드 체계 + 넛지

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 중간 도입 시나리오 지원 — 세션×git 인벤토리로 에피소드(주제 단위) 분할 소급 회고, 멀티 스펙(retro/specs/), 온보딩형 overview.md, SessionStart 넛지 훅.

**Architecture:** 스펙: `docs/superpowers/specs/2026-07-28-session-retro-v1.1-design.md`. 기존 코어(파서·velog·덱)는 무변경. 신규 스크립트 2개(inventory, nudge) + SKILL.md 3개 개정 + 문서 갱신.

**Tech Stack:** v1과 동일 (python3 표준 라이브러리, bash, pytest).

## Global Constraints

v1 계획의 Global Constraints 전부 유지(경로 공백 인용, 훅 exit 0, pip 의존 0, 커밋 재시도 등). 추가: 기존 테스트 49개는 깨지지 않아야 한다.

---

### Task 1: `inventory.py` — 세션 × git 교차표

**Files:**
- Create: `skills/retro/scripts/inventory.py`
- Test: `tests/test_inventory.py`

**Interfaces:**
- Consumes: `parse_transcript.parse_lines` (같은 디렉토리에서 import)
- Produces: CLI `inventory.py [--sessions <jsonl...>] [--repo DIR] [--out FILE]` → 마크다운 표(세션: 날짜/제목/시간/턴/도구실패/커밋, 미귀속 커밋 별도 표). 함수 `session_row(path) -> dict`, `git_commits(repo) -> list|None`, `assign(commits, rows) -> unassigned`.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_inventory.py`

```python
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro" / "scripts" / "inventory.py"

spec = importlib.util.spec_from_file_location("inventory", SCRIPT)
inv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inv)


def make_session(path, title, ts_list):
    lines = [json.dumps({"type": "ai-title", "title": title})]
    for i, ts in enumerate(ts_list):
        lines.append(json.dumps({
            "type": "user", "isSidechain": False, "timestamp": ts,
            "message": {"role": "user", "content": f"메시지 {i}"},
        }))
    path.write_text("\n".join(lines), encoding="utf-8")


def make_repo(tmp_path, commits):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    for msg, date in commits:
        (repo / "f.txt").write_text(msg)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", msg],
            cwd=repo, check=True,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date,
                 "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                 "PATH": "/usr/bin:/bin"},
        )
    return repo


def test_commit_assignment(tmp_path):
    s1 = tmp_path / "s1.jsonl"
    make_session(s1, "인증 구현", ["2026-07-10T10:00:00Z", "2026-07-10T11:00:00Z"])
    repo = make_repo(tmp_path, [
        ("feat: 로그인", "2026-07-10T10:30:00+00:00"),   # 세션 창 안
        ("chore: 옛날 작업", "2026-06-01T09:00:00+00:00"),  # 창 밖 → 미귀속
    ])
    rows = [inv.session_row(s1)]
    commits = inv.git_commits(str(repo))
    unassigned = inv.assign(commits, rows)
    assert len(rows[0]["commits"]) == 1 and "로그인" in rows[0]["commits"][0]["subject"]
    assert len(unassigned) == 1 and "옛날" in unassigned[0]["subject"]


def test_render_contains_table_and_orphan_commits(tmp_path):
    s1 = tmp_path / "s1.jsonl"
    make_session(s1, "배포 삽질", ["2026-07-12T09:00:00Z", "2026-07-12T09:40:00Z"])
    rows = [inv.session_row(s1)]
    text = inv.render(rows, [{"hash": "abc1234", "ts": rows[0]["first"], "subject": "고아 커밋"}], True)
    assert "배포 삽질" in text and "40분" in text
    assert "세션 기록이 없는 커밋" in text and "고아 커밋" in text


def test_no_git_graceful(tmp_path):
    assert inv.git_commits(str(tmp_path)) is None  # git 저장소 아님


def test_cli_out(tmp_path):
    s1 = tmp_path / "s1.jsonl"
    make_session(s1, "테스트", ["2026-07-01T10:00:00Z"])
    out = tmp_path / "inv.md"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--sessions", str(s1), "--repo", str(tmp_path), "--out", str(out)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 0 and "프로젝트 인벤토리" in out.read_text(encoding="utf-8")


def test_cli_no_sessions_exit_1(tmp_path):
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--sessions", str(tmp_path / "nope.jsonl"), "--repo", str(tmp_path)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 1
```

- [ ] **Step 2: 실패 확인** — `python3 -m pytest tests/test_inventory.py -q` → 수집 에러(파일 없음)

- [ ] **Step 3: 구현** — `skills/retro/scripts/inventory.py`

```python
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
    """커밋을 세션 시간창에 귀속시키고 미귀속 목록을 반환."""
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
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_inventory.py -q` → 전부 PASS
- [ ] **Step 5: 커밋** — `git add skills/retro/scripts/inventory.py tests/test_inventory.py && git commit -m "feat: 세션×git 인벤토리 스크립트 (에피소드 분할 재료)"`

---

### Task 2: 넛지 훅 `retro_nudge.py` + hooks.json/install.sh 갱신

**Files:**
- Create: `hooks/retro_nudge.py`
- Modify: `hooks/hooks.json` (SessionStart 추가), `install.sh` (두 훅 이벤트 등록으로 일반화), `tests/test_install.sh` (SessionStart 검증 추가)
- Test: `tests/test_nudge.sh`

**Interfaces:**
- Consumes: SessionStart stdin JSON (`cwd`, `source`)
- Produces: stdout JSON `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}` 또는 무출력. 항상 exit 0.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_nudge.sh`

```bash
#!/usr/bin/env bash
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/retro_nudge.py"
fails=0
t() { if eval "$2" >/dev/null 2>&1; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails+1)); fi; }
TMP=$(mktemp -d)
export HOME="$TMP"
json() { printf '{"cwd":"%s","source":"%s","hook_event_name":"SessionStart","session_id":"x","transcript_path":""}' "$1" "$2"; }

# A) 활성 프로젝트 + 스펙 이후 새 재료 → 체크포인트 넛지
mkdir -p "$TMP/proj/retro/specs" "$TMP/proj/retro/archive"
echo spec > "$TMP/proj/retro/specs/ep1.md"
touch -d "2020-01-01" "$TMP/proj/retro/specs/ep1.md"
echo new > "$TMP/proj/retro/archive/2026-07-28-abc.jsonl"
out=$(json "$TMP/proj" startup | python3 "$HOOK")
t "fresh material nudges checkpoint" "echo \"$out\" | grep -q '체크포인트'"
t "output is valid hook json" "echo \"$out\" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d[\"hookSpecificOutput\"][\"hookEventName\"]==\"SessionStart\"'"

# B) compact 재시작 → 침묵
out=$(json "$TMP/proj" compact | python3 "$HOOK")
t "compact is silent" "[ -z \"$out\" ]"

# C) 미활성 + 세션 3개 → 소급 안내
mkdir -p "$TMP/proj2"
MUNGED=$(python3 -c "import re,sys;print(re.sub(r'[^A-Za-z0-9]','-','$TMP/proj2'))")
mkdir -p "$TMP/.claude/projects/$MUNGED"
for i in 1 2 3; do echo x > "$TMP/.claude/projects/$MUNGED/s$i.jsonl"; done
out=$(json "$TMP/proj2" startup | python3 "$HOOK")
t "inactive project suggests backfill" "echo \"$out\" | grep -q '소급'"

# D) 해당 없음 → 무출력, exit 0
mkdir -p "$TMP/proj3"
out=$(json "$TMP/proj3" startup | python3 "$HOOK"); rc=$?
t "nothing to say is silent exit 0" "[ -z \"$out\" ] && [ $rc -eq 0 ]"

# E) 쓰레기 입력 → exit 0
echo garbage | python3 "$HOOK"; rc=$?
t "garbage exit 0" "[ $rc -eq 0 ]"

rm -rf "$TMP"
echo "failures: $fails"
exit $fails
```

- [ ] **Step 2: 실패 확인** — `bash tests/test_nudge.sh` → FAIL 다수

- [ ] **Step 3: 구현** — `hooks/retro_nudge.py`

```python
#!/usr/bin/env python3
"""SessionStart 훅: 회고 재료가 쌓였으면 Claude에게 넛지 컨텍스트를 주입한다.

어떤 실패에도 exit 0. 출력이 없으면 아무 일도 일어나지 않는다. AI 호출 없음.
"""
import json
import re
import sys
from pathlib import Path


def build_context(data):
    if str(data.get("source", "")) == "compact":
        return None  # 세션 중간 압축 재시작에는 넛지하지 않는다
    cwd = Path(str(data.get("cwd", "")) or ".")
    retro = cwd / "retro"
    if retro.is_dir():
        spec_files = list((retro / "specs").glob("*.md")) if (retro / "specs").is_dir() else []
        spec_files += [p for p in (retro / "spec.md", retro / "overview.md") if p.is_file()]
        newest_spec = max((p.stat().st_mtime for p in spec_files), default=0.0)
        archive = retro / "archive"
        fresh = [p for p in archive.glob("*.jsonl") if p.stat().st_mtime > newest_spec] if archive.is_dir() else []
        if fresh:
            return (
                f"[session-retro] 회고 스펙 갱신 이후 백업된 세션이 {len(fresh)}개 있습니다. "
                "사용자가 작업을 마무리하거나 정리를 원하는 시점에 /retro 체크포인트를 "
                "한 문장으로 제안하세요. 대화 시작부터 먼저 꺼내지는 마세요."
            )
        return None
    munged = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    proj = Path.home() / ".claude" / "projects" / munged
    sessions = list(proj.glob("*.jsonl")) if proj.is_dir() else []
    if len(sessions) >= 3:
        return (
            f"[session-retro] 이 프로젝트에는 세션 기록이 {len(sessions)}개 있지만 회고가 "
            "활성화되지 않았습니다. 사용자가 회고·블로그·발표·정리를 언급하면 /retro 소급 모드"
            "(세션×git 교차로 에피소드 분할)를 안내하세요."
        )
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        ctx = build_context(data)
        if ctx:
            print(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}},
                ensure_ascii=False,
            ))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: hooks.json에 SessionStart 항목 추가** (기존 SessionEnd/PreCompact 유지, 같은 형식으로 `retro_nudge.py` 명령 추가)

- [ ] **Step 5: install.sh 일반화** — 병합 파이썬에서 `(이벤트, 스크립트)` 목록을 순회: `("SessionEnd", "archive_transcript.py")`, `("PreCompact", "archive_transcript.py")`, `("SessionStart", "retro_nudge.py")`. 멱등 판정은 스크립트 파일명 포함 여부로(기존과 동일).

- [ ] **Step 6: tests/test_install.sh에 검증 추가** — SessionStart에 retro_nudge.py 등록 + 2회 실행 시 중복 없음.

- [ ] **Step 7: 통과 확인** — `bash tests/test_nudge.sh && bash tests/test_install.sh && bash tests/test_hook.sh` → 전부 PASS
- [ ] **Step 8: 커밋** — `git add hooks/ install.sh tests/ && git commit -m "feat: SessionStart 넛지 훅 — 체크포인트 제안·소급 모드 안내 (비용 0)"`

---

### Task 3: retro SKILL.md 개정 (소급/증분 모드, 멀티 스펙, overview, 가드레일, 마이그레이션)

**Files:** Modify: `skills/retro/SKILL.md` — 설계서 §3~§5의 내용을 반영해 전면 개정. 필수 포함:
- 모드 판정 규칙(§5), 소급 모드 4단계(inventory 실행 명령 `python3 "<skill-dir>/scripts/inventory.py" --out retro/.timeline/inventory.md` 포함, 에피소드 1~2개씩 생성, 사용자 인터뷰로 소실 구간 보완)
- 증분 모드(병합 vs 신규 제안), 분량 가드레일(문제 4개 초과/1편 분량 초과 → 부작 분할 제안 + 시리즈명)
- 스펙 경로 규칙 `retro/specs/YYYY-MM-DD-<slug>.md`(내용 형식은 v1 spec.md 형식 그대로 유지), 구 spec.md 마이그레이션 제안
- overview.md 전체 템플릿(설계서 §4 그대로), 에피소드 변경 시 overview 갱신 규칙
- 초기화 mkdir에 `retro/specs` 추가
- 기존 증류 규칙·톤·이미지 큐레이션 섹션은 유지

**검증:** `python3 -m pytest tests/test_skill_files.py -q` PASS (frontmatter·참조 경로) + SKILL.md에 `scripts/inventory.py` 백틱 참조가 있어 존재 검증에 걸리는지 확인.
**커밋:** `git commit -m "feat: retro 스킬 v1.1 — 소급/증분 모드, 에피소드 멀티 스펙, overview, 분량 가드레일"`

---

### Task 4: retro-blog / retro-ppt SKILL.md 개정

**Files:** Modify: `skills/retro-blog/SKILL.md`, `skills/retro-ppt/SKILL.md`
- retro-blog 전제·절차 갱신: `retro/specs/*.md` 목록에서 선택(기본: 최근 갱신, 1개면 바로), 구 `retro/spec.md` 폴백, 부작 스펙은 부별 생성 + velog 시리즈명 제안(연동은 v2임을 명시)
- retro-ppt 절차 갱신: 발표 대상 선택 — 에피소드 1개(스펙) 또는 프로젝트 전체(overview.md 기반 서사: 개요→에피소드 하이라이트→지뢰밭 지도→다음 단계)

**검증:** `python3 -m pytest tests/test_skill_files.py -q` PASS.
**커밋:** `git commit -m "feat: retro-blog·retro-ppt v1.1 — 에피소드 스펙 선택, overview 기반 전체 발표"`

---

### Task 5: 문서 갱신 + 전체 검증

**Files:** Modify: `README.md`(트리거 표에 소급 행 이미 있음 — 소급 모드·overview·넛지 설명 3~5줄 추가), `docs/index.html`(트리거 표 "과거 세션" 행을 소급 모드 설명으로 보강 + FAQ에 "이미 한참 진행된 프로젝트인데요?" 항목 추가 + 파이프라인 도식에 specs/overview 반영), 설계서·계획서 커밋.

- [ ] 전체 테스트: `python3 -m pytest tests/ -q && bash tests/test_hook.sh && bash tests/test_nudge.sh && bash tests/test_install.sh` → 전부 PASS
- [ ] 실전 스모크: 이 프로젝트에서 `python3 "skills/retro/scripts/inventory.py" --out /tmp/inv.md` 실행 → 이 세션+커밋 매칭 확인
- [ ] 커밋 후 finishing-a-development-branch로 main 병합

## Self-Review 결과

- 스펙 커버리지: v1.1 설계 §3(T3 구조), §4(T3 overview), §5(T3), §6(T4), §7(T2), §8(T1), §9(T1·T2 테스트), §10(T5). 갭 없음.
- 플레이스홀더: T1·T2는 실코드 전문, T3~T5는 설계서의 확정 계약(§3~§6 원문)을 반영하는 문서 편집으로 내용 근거가 설계서에 실재. 통과.
- 일관성: inventory CLI 시그니처(T1 정의 ↔ T3 SKILL.md 호출), 넛지 문구(T2 구현 ↔ 테스트 grep), specs/ 경로(T3 ↔ T4) 일치.
