# session-retro 플러그인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code 세션의 시행착오를 회고 스펙으로 증류해 velog 블로그 초안과 단일 파일 HTML 발표 덱으로 변환하는 플러그인(스킬 3개 + 백업 훅 + 스크립트)을 구현한다.

**Architecture:** `retro/spec.md`를 단일 진실 소스로 두는 스펙-퍼스트 구조. 훅은 세션 JSONL을 프로젝트 `retro/archive/`로 복사만 하고(영속화), `retro` 스킬이 파서로 타임라인을 만들어 증류하며, `retro-blog`/`retro-ppt`는 같은 스펙을 각각 velog MD(+초안 업로드)와 HTML 덱으로 렌더링한다. 상세 설계: `docs/superpowers/specs/2026-07-28-session-retro-design.md`.

**Tech Stack:** bash + python3(표준 라이브러리만, pip 의존 0), pytest(테스트 전용), velog 비공식 GraphQL/REST API, 단일 파일 HTML/CSS/JS.

## Global Constraints

- python3 표준 라이브러리만 사용한다(런타임 pip 의존 0). 테스트만 pytest 허용.
- 이 저장소 경로에는 공백이 있다(`/mnt/c/dev/2026 soma/velog-ppt-skills`) — 모든 셸 명령·스크립트에서 경로를 반드시 따옴표로 감싼다.
- 훅은 어떤 실패에도 exit 0 (세션을 절대 방해하지 않음). 오류는 `retro/archive/.hook.log`에만 기록.
- 토큰은 `~/.config/velog-retro/tokens.json`(권한 0600)에만 저장. 로그·에러 메시지·git에 절대 노출 금지.
- velog 업로드는 항상 `is_temp: true`(임시저장) 전용. 공개 발행은 v1 미지원.
- HTML 덱은 외부 요청 0(오프라인 동작), 이미지는 data URI 임베드.
- 스킬 이름: `retro`, `retro-blog`, `retro-ppt`. 산출물 디렉토리 구조는 스펙 §5.2를 따른다.
- 각 태스크 완료 시 커밋한다.

---

### Task 1: 백업 훅 (`archive_transcript.py` + `hooks.json`)

**Files:**
- Create: `hooks/archive_transcript.py`
- Create: `hooks/hooks.json`
- Test: `tests/test_hook.sh`

**Interfaces:**
- Consumes: 없음 (stdin으로 Claude Code 훅 JSON: `transcript_path`, `cwd`, `session_id`, `hook_event_name`)
- Produces: `<cwd>/retro/archive/<YYYY-MM-DD>-<sid8>.jsonl` (SessionEnd), `<YYYY-MM-DD>-<sid8>-precompact-<HHMMSS>.jsonl` (PreCompact). Task 8의 install.sh가 이 스크립트 경로를 settings.json에 등록한다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_hook.sh`

```bash
#!/usr/bin/env bash
# 백업 훅 테스트. 실패 개수를 종료 코드로 반환.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/archive_transcript.py"
fails=0
t() { if eval "$2" >/dev/null 2>&1; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails+1)); fi; }
TMP=$(mktemp -d)
mkdir -p "$TMP/proj/retro"
echo '{"type":"user"}' > "$TMP/transcript.jsonl"
json() { printf '{"transcript_path":"%s","cwd":"%s","session_id":"abcdef1234567890","hook_event_name":"%s"}' "$1" "$2" "$3"; }

# 1) SessionEnd: retro/ 있는 프로젝트 → archive에 복사
json "$TMP/transcript.jsonl" "$TMP/proj" SessionEnd | python3 "$HOOK"
t "SessionEnd copies" "ls \"$TMP/proj/retro/archive/\"*-abcdef12.jsonl"

# 2) PreCompact: -precompact-HHMMSS 접미사로 별도 보존
json "$TMP/transcript.jsonl" "$TMP/proj" PreCompact | python3 "$HOOK"
t "PreCompact suffixed" "ls \"$TMP/proj/retro/archive/\"*-abcdef12-precompact-*.jsonl"

# 3) retro/ 없는 프로젝트 → 아무것도 만들지 않고 exit 0
mkdir -p "$TMP/proj2"
json "$TMP/transcript.jsonl" "$TMP/proj2" SessionEnd | python3 "$HOOK"; rc=$?
t "no retro -> no copy, exit 0" "[ $rc -eq 0 ] && [ ! -e \"$TMP/proj2/retro\" ]"

# 4) 쓰레기 stdin → exit 0
echo 'garbage' | python3 "$HOOK"; rc=$?
t "garbage stdin exit 0" "[ $rc -eq 0 ]"

# 5) transcript 파일 없음 → exit 0, 복사 없음
json "$TMP/nope.jsonl" "$TMP/proj" SessionEnd | python3 "$HOOK"; rc=$?
t "missing transcript exit 0" "[ $rc -eq 0 ]"

# 6) 로그 파일 생성 확인
t "hook log written" "grep -q SessionEnd \"$TMP/proj/retro/archive/.hook.log\""

rm -rf "$TMP"
echo "failures: $fails"
exit $fails
```

- [ ] **Step 2: 실패 확인**

Run: `bash tests/test_hook.sh`
Expected: FAIL 다수 (hooks/archive_transcript.py 없음 → python3가 파일을 못 찾아 모든 케이스 실패)

- [ ] **Step 3: 최소 구현** — `hooks/archive_transcript.py`

```python
#!/usr/bin/env python3
"""SessionEnd/PreCompact 훅: retro/가 있는 프로젝트에서만 트랜스크립트를 retro/archive/로 백업.

어떤 실패에도 exit 0 — 세션을 절대 방해하지 않는다. 오류는 .hook.log에만 남긴다.
"""
import datetime
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        transcript = Path(str(data.get("transcript_path", "")))
        cwd = Path(str(data.get("cwd", "")))
        sid = (str(data.get("session_id", "")) or "unknown")[:8]
        event = str(data.get("hook_event_name", ""))
        retro = cwd / "retro"
        if not retro.is_dir() or not transcript.is_file():
            return 0
        archive = retro / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now()
        if event == "PreCompact":
            name = f"{now:%Y-%m-%d}-{sid}-precompact-{now:%H%M%S}.jsonl"
        else:
            name = f"{now:%Y-%m-%d}-{sid}.jsonl"
        shutil.copy2(transcript, archive / name)
        with open(archive / ".hook.log", "a", encoding="utf-8") as f:
            f.write(f"{now:%Y-%m-%dT%H:%M:%S} {event} {transcript} -> {name}\n")
    except Exception as e:  # noqa: BLE001 — 훅은 절대 실패를 전파하지 않는다
        try:
            with open(Path(str(data.get("cwd", "."))) / "retro" / "archive" / ".hook.log", "a", encoding="utf-8") as f:
                f.write(f"ERROR {e}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: `hooks/hooks.json` 작성** (플러그인 규격 — `${CLAUDE_PLUGIN_ROOT}` 사용)

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/archive_transcript.py\""
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/archive_transcript.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `bash tests/test_hook.sh`
Expected: PASS ×6, `failures: 0`, exit 0

- [ ] **Step 6: 커밋**

```bash
git add hooks/ tests/test_hook.sh
git commit -m "feat: 세션 트랜스크립트 백업 훅 (SessionEnd/PreCompact, opt-in, 무해성 보장)"
```

---

### Task 2: 트랜스크립트 파서 (`parse_transcript.py`)

**Files:**
- Create: `skills/retro/scripts/parse_transcript.py`
- Create: `tests/fixtures/sample_session.jsonl`
- Test: `tests/test_parse_transcript.py`

**Interfaces:**
- Consumes: 세션 JSONL 파일(비공식 스키마 — 방어적 파싱)
- Produces: CLI `python3 parse_transcript.py FILE... [--max-chars N] [--include-sidechains] [--out PATH]` → 타임라인 마크다운(기본 stdout, `--out`이면 파일). 내부 함수 `parse_lines(lines, include_sidechains=False) -> tuple[list[dict], dict]`(events, stats), `render_markdown(name, events, stats, max_chars) -> str`. events 항목: `{"ts": datetime|None, "kind": "text"|"tool_use"|"tool_error", "role": "user"|"assistant", "text": str, "tool": str}`. stats: `{"turns", "tools", "errors", "skipped_lines", "skipped_records", "models", "titles", "first_ts", "last_ts"}`. Task 5의 retro SKILL.md가 이 CLI를 호출한다.

- [ ] **Step 1: fixture 작성** — `tests/fixtures/sample_session.jsonl` (아래 8줄 그대로, 한 줄당 JSON 하나)

```
{"type":"last-prompt","sessionId":"s1"}
{"type":"user","isSidechain":false,"timestamp":"2026-07-28T08:00:00.000Z","message":{"role":"user","content":"로그인 버그 고쳐줘"}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-07-28T08:01:00.000Z","message":{"role":"assistant","model":"claude-fable-5","content":[{"type":"text","text":"원인을 찾아보겠습니다."},{"type":"tool_use","name":"Bash","input":{"command":"pytest -x","description":"테스트 실행"}}]}}
{"type":"user","isSidechain":false,"timestamp":"2026-07-28T08:02:00.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","is_error":true,"content":[{"type":"text","text":"AssertionError in test_login"}]}]},"toolUseResult":{"error":"AssertionError"}}
{"type":"user","isSidechain":true,"timestamp":"2026-07-28T08:03:00.000Z","message":{"role":"user","content":"사이드체인 메시지"}}
{"type":"assistant","isSidechain":false,"timestamp":"2026-07-28T08:04:00.000Z","message":{"role":"assistant","model":"claude-fable-5","content":[{"type":"text","text":"세션 만료 로직이 원인이었습니다. 수정했습니다."}]}}
{"type":"file-history-snapshot","snapshot":{}}
{"type":"ai-title","title":"로그인 버그 수정"}
```

(7번째 줄 앞에 `{not json` 같은 깨진 라인을 테스트에서 문자열로 직접 추가한다 — fixture 파일은 유효 JSON만 유지해 재사용성을 높인다.)

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_parse_transcript.py`

```python
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro" / "scripts" / "parse_transcript.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_session.jsonl"

spec = importlib.util.spec_from_file_location("parse_transcript", SCRIPT)
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)


def fixture_lines():
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def test_skips_malformed_and_unknown_records():
    lines = fixture_lines() + ["{not json", '{"type":"mystery-record"}']
    events, stats = pt.parse_lines(lines)
    assert stats["skipped_lines"] == 1
    assert stats["skipped_records"].get("file-history-snapshot") == 1
    assert stats["skipped_records"].get("mystery-record") == 1
    assert all(e["kind"] in ("text", "tool_use", "tool_error") for e in events)


def test_sidechain_excluded_by_default_included_with_flag():
    events, _ = pt.parse_lines(fixture_lines())
    assert not any("사이드체인" in e["text"] for e in events)
    events2, _ = pt.parse_lines(fixture_lines(), include_sidechains=True)
    assert any("사이드체인" in e["text"] for e in events2)


def test_tool_error_highlighted_in_markdown():
    events, stats = pt.parse_lines(fixture_lines())
    md = pt.render_markdown("sample", events, stats, max_chars=80_000)
    assert "❌" in md
    assert "AssertionError" in md
    assert stats["errors"] == 1


def test_tool_use_summarized_with_description():
    events, _ = pt.parse_lines(fixture_lines())
    tools = [e for e in events if e["kind"] == "tool_use"]
    assert tools and tools[0]["tool"] == "Bash"
    assert "테스트 실행" in tools[0]["text"]


def test_long_text_truncated():
    line = (
        '{"type":"assistant","isSidechain":false,"timestamp":"2026-07-28T08:05:00.000Z",'
        '"message":{"role":"assistant","content":[{"type":"text","text":"%s"}]}}' % ("가" * 3000)
    )
    events, stats = pt.parse_lines([line])
    md = pt.render_markdown("t", events, stats, max_chars=80_000)
    assert "생략" in md
    assert "가" * 1300 not in md


def test_chunking_inserts_part_markers():
    lines = fixture_lines() * 40
    events, stats = pt.parse_lines(lines)
    md = pt.render_markdown("t", events, stats, max_chars=2_000)
    assert "PART 1/" in md


def test_stats_summary_present():
    events, stats = pt.parse_lines(fixture_lines())
    md = pt.render_markdown("sample", events, stats, max_chars=80_000)
    assert "로그인 버그 수정" in md  # ai-title
    assert "claude-fable-5" in md
    assert "도구 호출: 1" in md


def test_main_end_to_end(tmp_path):
    out = tmp_path / "timeline.md"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "세션 타임라인" in text


def test_main_no_valid_file_exits_1(tmp_path):
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.jsonl")],
        capture_output=True, text=True,
    ).returncode
    assert rc == 1


@pytest.mark.skipif(not any(Path.home().glob(".claude/projects/*/*.jsonl")), reason="로컬 실세션 없음")
def test_smoke_real_transcript(tmp_path):
    real = max(Path.home().glob(".claude/projects/*/*.jsonl"), key=lambda p: p.stat().st_mtime)
    out = tmp_path / "real.md"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), str(real), "--out", str(out)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 0 and out.stat().st_size > 0
```

- [ ] **Step 3: 실패 확인**

Run: `python3 -m pytest tests/test_parse_transcript.py -v`
Expected: 수집 단계 에러(FileNotFoundError: parse_transcript.py 없음)

- [ ] **Step 4: 구현** — `skills/retro/scripts/parse_transcript.py`

```python
#!/usr/bin/env python3
"""Claude Code 세션 JSONL → 타임라인 마크다운.

스키마가 비공식·유동적이므로 방어적으로 파싱한다: 모르는 레코드/깨진 라인은
스킵하고 개수만 보고한다. 사이드체인(서브에이전트)은 기본 제외.
표준 라이브러리만 사용.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

TEXT_LIMIT = 1500      # 이보다 긴 텍스트는 앞 1200자 + 생략 표기
TEXT_KEEP = 1200
TOOL_INPUT_LIMIT = 160


def _ts(obj):
    raw = obj.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _tool_summary(block):
    inp = block.get("input") or {}
    for key in ("description", "command", "file_path", "prompt", "query", "pattern"):
        if inp.get(key):
            text = str(inp[key])
            break
    else:
        text = json.dumps(inp, ensure_ascii=False)
    if len(text) > TOOL_INPUT_LIMIT:
        text = text[:TOOL_INPUT_LIMIT] + "…"
    return text


def _result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def parse_lines(lines, include_sidechains=False):
    events = []
    stats = {
        "turns": 0, "tools": 0, "errors": 0, "skipped_lines": 0,
        "skipped_records": {}, "models": set(), "titles": [],
        "first_ts": None, "last_ts": None,
    }
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            stats["skipped_lines"] += 1
            continue
        rtype = obj.get("type")
        if rtype == "ai-title":
            title = obj.get("title") or obj.get("value")
            if title:
                stats["titles"].append(str(title))
            continue
        if rtype not in ("user", "assistant"):
            if rtype:
                stats["skipped_records"][rtype] = stats["skipped_records"].get(rtype, 0) + 1
            continue
        if obj.get("isSidechain") and not include_sidechains:
            continue
        ts = _ts(obj)
        if ts:
            stats["first_ts"] = min(stats["first_ts"] or ts, ts)
            stats["last_ts"] = max(stats["last_ts"] or ts, ts)
        message = obj.get("message") or {}
        model = message.get("model")
        if model:
            stats["models"].add(str(model))
        content = message.get("content")
        role = "user" if rtype == "user" else "assistant"
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        if not isinstance(blocks, list):
            continue
        emitted_text = False
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and str(block.get("text", "")).strip():
                events.append({"ts": ts, "kind": "text", "role": role,
                               "text": str(block["text"]).strip(), "tool": ""})
                emitted_text = True
            elif btype == "tool_use":
                stats["tools"] += 1
                events.append({"ts": ts, "kind": "tool_use", "role": role,
                               "text": _tool_summary(block), "tool": str(block.get("name", "?"))})
            elif btype == "tool_result":
                is_error = bool(block.get("is_error"))
                tur = obj.get("toolUseResult")
                if isinstance(tur, dict) and tur.get("error"):
                    is_error = True
                if is_error:
                    stats["errors"] += 1
                    events.append({"ts": ts, "kind": "tool_error", "role": role,
                                   "text": _result_text(block)[:300], "tool": ""})
        if emitted_text:
            stats["turns"] += 1
    return events, stats


def _clip(text):
    if len(text) > TEXT_LIMIT:
        return text[:TEXT_KEEP] + f"… (+{len(text) - TEXT_KEEP}자 생략)"
    return text


def render_markdown(name, events, stats, max_chars=80_000):
    head = [f"# 세션 타임라인: {name}", ""]
    if stats["titles"]:
        head.append(f"- 세션 제목: {' / '.join(stats['titles'])}")
    if stats["first_ts"] and stats["last_ts"]:
        dur = stats["last_ts"] - stats["first_ts"]
        head.append(
            f"- 기간: {stats['first_ts']:%Y-%m-%d %H:%M} ~ {stats['last_ts']:%H:%M} ({int(dur.total_seconds() // 60)}분)"
        )
    head.append(
        f"- 턴: {stats['turns']} / 도구 호출: {stats['tools']} (실패 {stats['errors']}) / 모델: {', '.join(sorted(stats['models'])) or '?'}"
    )
    skipped = stats["skipped_lines"] + sum(stats["skipped_records"].values())
    if skipped:
        head.append(f"- 스킵된 라인/레코드: {skipped} (방어적 파싱)")
    head += ["", "## 대화", ""]

    body_lines = []
    for e in events:
        t = f"[{e['ts']:%H:%M}] " if e["ts"] else ""
        if e["kind"] == "text":
            icon = "👤 사용자" if e["role"] == "user" else "🤖 Claude"
            body_lines.append(f"{t}{icon}: {_clip(e['text'])}")
        elif e["kind"] == "tool_use":
            body_lines.append(f"{t}   [도구: {e['tool']}] {e['text']}")
        else:
            body_lines.append(f"{t}   ❌ [도구 실패] {e['text']}")
        body_lines.append("")

    text = "\n".join(head + body_lines)
    if len(text) <= max_chars:
        return text
    # 파트 분할: 이벤트 라인 단위로 자른다
    parts, cur, size = [], [], 0
    for line in body_lines:
        if size + len(line) > max_chars and cur:
            parts.append(cur)
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        parts.append(cur)
    out = head[:]
    for i, part in enumerate(parts, 1):
        out.append(f"<!-- ── PART {i}/{len(parts)} ── -->")
        out.extend(part)
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="세션 JSONL → 타임라인 마크다운")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--max-chars", type=int, default=80_000)
    ap.add_argument("--include-sidechains", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    sections = []
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"경고: 파일 없음 — {p}", file=sys.stderr)
            continue
        events, stats = parse_lines(
            p.read_text(encoding="utf-8", errors="replace").splitlines(),
            include_sidechains=args.include_sidechains,
        )
        sections.append(render_markdown(p.name, events, stats, max_chars=args.max_chars))
    if not sections:
        print("에러: 유효한 파일이 없습니다", file=sys.stderr)
        return 1
    result = "\n\n---\n\n".join(sections)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(result, encoding="utf-8")
        print(f"작성됨: {args.out} ({len(result):,}자)")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_parse_transcript.py -v`
Expected: 전부 PASS (실세션 스모크 포함 — 이 머신엔 실세션이 있음)

- [ ] **Step 6: 커밋**

```bash
git add skills/retro/scripts/parse_transcript.py tests/
git commit -m "feat: 세션 JSONL 타임라인 파서 (방어적 파싱, 에러 하이라이트, 청크 분할)"
```

---

### Task 3: velog 업로더 1/2 — 토큰 관리 + 이미지 업로드 (`velog_publish.py`)

**Files:**
- Create: `skills/retro-blog/scripts/velog_publish.py`
- Test: `tests/test_velog_publish.py`

**Interfaces:**
- Consumes: 없음
- Produces: 모듈 함수 — `_http(url, method="GET", headers=None, data=None) -> tuple[int, list[tuple[str, str]], bytes]`(테스트가 monkeypatch하는 유일한 네트워크 지점), `load_tokens() -> dict|None`, `save_tokens(dict)`, `cookie_header(tokens) -> str`, `upload_image(path: Path, tokens) -> str`(CDN URL 반환), `rewrite_images(md_text: str, md_dir: Path, tokens) -> tuple[str, int]`, CLI 서브커맨드 `setup`. 상수 `UPLOAD_URL = "https://v3.velog.io/api/files/v3/upload"`, `GRAPHQL_URL = "https://v3.velog.io/graphql"`, `TOKEN_PATH = ~/.config/velog-retro/tokens.json`. Task 4가 이 함수들 위에 publish를 얹는다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_velog_publish.py` (Task 3 범위 부분)

```python
import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro-blog" / "scripts" / "velog_publish.py"

spec = importlib.util.spec_from_file_location("velog_publish", SCRIPT)
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "TOKEN_PATH", tmp_path / "cfg" / "tokens.json")
    return tmp_path


def test_setup_writes_tokens_0600(home, monkeypatch):
    answers = iter(["at-123", "rt-456"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert vp.cmd_setup() == 0
    saved = json.loads(vp.TOKEN_PATH.read_text())
    assert saved == {"access_token": "at-123", "refresh_token": "rt-456"}
    assert stat.S_IMODE(vp.TOKEN_PATH.stat().st_mode) == 0o600


def test_cookie_header(home):
    hdr = vp.cookie_header({"access_token": "a", "refresh_token": "r"})
    assert "access_token=a" in hdr and "refresh_token=r" in hdr


def test_upload_image_returns_cdn_url(home, tmp_path, monkeypatch):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG fake")
    calls = {}

    def fake_http(url, method="GET", headers=None, data=None):
        calls["url"], calls["headers"], calls["data"] = url, headers, data
        return 200, [], json.dumps({"path": "https://velog.velcdn.com/images/u/x.png"}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    url = vp.upload_image(img, {"access_token": "a", "refresh_token": "r"})
    assert url == "https://velog.velcdn.com/images/u/x.png"
    assert calls["url"] == vp.UPLOAD_URL
    ctype = dict(calls["headers"])["Content-Type"]
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="image"' in calls["data"] and b'name="type"' in calls["data"] and b"post" in calls["data"]
    assert "Cookie" in dict(calls["headers"])


def test_rewrite_images_uploads_local_and_skips_remote(home, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.png").write_bytes(b"img")
    md = "![캡션](assets/a.png)\n![원격](https://example.com/b.png)\n"
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/a.png")
    new_md, n = vp.rewrite_images(md, tmp_path, {"access_token": "a"})
    assert n == 1
    assert "https://velog.velcdn.com/u/a.png" in new_md
    assert "https://example.com/b.png" in new_md


def test_upload_http_error_raises(home, tmp_path, monkeypatch):
    img = tmp_path / "x.png"
    img.write_bytes(b"img")
    monkeypatch.setattr(vp, "_http", lambda *a, **k: (500, [], b"boom"))
    with pytest.raises(vp.VelogError):
        vp.upload_image(img, {"access_token": "a"})
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_velog_publish.py -v`
Expected: 수집 에러 (velog_publish.py 없음)

- [ ] **Step 3: 구현** — `skills/retro-blog/scripts/velog_publish.py` (Task 3 범위)

```python
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
```

(CLI `main`은 Task 4에서 publish와 함께 완성한다. 이 시점에는 `if __name__ == "__main__": sys.exit(cmd_setup() if len(sys.argv) > 1 and sys.argv[1] == "setup" else 1)` 임시 엔트리로 둔다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_velog_publish.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/retro-blog/scripts/velog_publish.py tests/test_velog_publish.py
git commit -m "feat: velog 업로더 — 토큰 관리(0600)·회전, multipart 이미지 CDN 업로드"
```

---

### Task 4: velog 업로더 2/2 — WritePost 초안 업로드 + publish CLI

**Files:**
- Modify: `skills/retro-blog/scripts/velog_publish.py` (함수 추가)
- Test: `tests/test_velog_publish.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 3의 `_http`, `load_tokens`, `rewrite_images`, `rotate_tokens`, `cookie_header`, `VelogError`
- Produces: `parse_frontmatter(md_text) -> tuple[dict, str]`(meta, body), `write_post_draft(title, body, tags, thumbnail, tokens) -> dict`(응답 writePost 객체), `cmd_publish(md_path: str, draft: bool = True) -> int`, CLI: `velog_publish.py setup | publish <md> --draft`. Task 6의 retro-blog SKILL.md가 이 CLI와 종료 코드(0/2/3/4/5)에 의존한다.

- [ ] **Step 1: 정확한 mutation 확인** — 레퍼런스 구현에서 실제 mutation 문자열을 가져온다

Run: `curl -sL "https://raw.githubusercontent.com/stoneHee99/velog-mcp/main/src/velog-client.ts" | grep -n -B2 -A25 -i "writePost"`
Expected: `WritePost` mutation의 정확한 GraphQL 문자열과 input 필드. 성공하면 그 문자열을 그대로 `WRITE_POST_MUTATION` 상수에 사용. 네트워크 실패 시 아래 기본값 사용(조사에서 확인된 필드: title, body, tags, is_markdown, is_temp, is_private, url_slug, thumbnail, series_id, token):

```python
WRITE_POST_MUTATION = """
mutation WritePost($input: WritePostInput!) {
  writePost(input: $input) {
    id
    url_slug
  }
}
""".strip()
```

- [ ] **Step 2: 실패하는 테스트 추가** — `tests/test_velog_publish.py`에 append

```python
MD = """---
title: 테스트 회고
tags: [Claude Code, 회고]
---

본문입니다.

![스크린샷](assets/a.png)
"""


def test_parse_frontmatter():
    meta, body = vp.parse_frontmatter(MD)
    assert meta["title"] == "테스트 회고"
    assert meta["tags"] == ["Claude Code", "회고"]
    assert body.startswith("본문입니다.")


def test_parse_frontmatter_missing_title():
    meta, _ = vp.parse_frontmatter("---\ntags: []\n---\n본문")
    assert "title" not in meta


def test_write_post_draft_payload(home, monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["url"], captured["data"] = url, json.loads(data)
        return 200, [], json.dumps({"data": {"writePost": {"id": "p-1", "url_slug": "slug"}}}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    result = vp.write_post_draft("제목", "본문", ["a"], None, {"access_token": "a", "refresh_token": "r"})
    assert result["id"] == "p-1"
    assert captured["url"] == vp.GRAPHQL_URL
    inp = captured["data"]["variables"]["input"]
    assert inp["is_temp"] is True and inp["is_markdown"] is True
    assert inp["title"] == "제목" and inp["tags"] == ["a"]


def test_write_post_graphql_error_raises(home, monkeypatch):
    monkeypatch.setattr(
        vp, "_http",
        lambda *a, **k: (200, [], json.dumps({"errors": [{"message": "nope"}]}).encode()),
    )
    with pytest.raises(vp.VelogError):
        vp.write_post_draft("t", "b", [], None, {"access_token": "a"})


def test_token_rotation_persisted(home, monkeypatch):
    vp.save_tokens({"access_token": "old", "refresh_token": "r"})

    def fake_http(url, method="GET", headers=None, data=None):
        return 200, [("Set-Cookie", "access_token=new; Path=/; HttpOnly")], json.dumps(
            {"data": {"writePost": {"id": "p", "url_slug": "s"}}}
        ).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    tokens = vp.load_tokens()
    vp.write_post_draft("t", "b", [], None, tokens)
    assert vp.load_tokens()["access_token"] == "new"


def test_cmd_publish_end_to_end(home, tmp_path, monkeypatch):
    blog = tmp_path / "out" / "blog"
    blog.mkdir(parents=True)
    (blog / "post.md").write_text(MD, encoding="utf-8")
    assets = blog / "assets"
    assets.mkdir()
    (assets / "a.png").write_bytes(b"img")
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/a.png")
    monkeypatch.setattr(vp, "write_post_draft", lambda *a, **k: {"id": "p-9", "url_slug": "s"})
    rc = vp.cmd_publish(str(blog / "post.md"))
    assert rc == 0
    published = (blog / "post.published.md").read_text(encoding="utf-8")
    assert "velcdn.com" in published


def test_cmd_publish_without_tokens_exit_2(home, tmp_path):
    md = tmp_path / "p.md"
    md.write_text(MD, encoding="utf-8")
    assert vp.cmd_publish(str(md)) == 2


def test_cmd_publish_without_title_exit_5(home, tmp_path):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text("제목 frontmatter 없음", encoding="utf-8")
    assert vp.cmd_publish(str(md)) == 5


def test_cmd_publish_auth_error_exit_2(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD.replace("![스크린샷](assets/a.png)", ""), encoding="utf-8")

    def raise_auth(*a, **k):
        raise vp.VelogError("인증 실패(401) — 토큰 만료 가능성. setup을 다시 실행하세요.")

    monkeypatch.setattr(vp, "write_post_draft", raise_auth)
    assert vp.cmd_publish(str(md)) == 2
```

- [ ] **Step 3: 실패 확인**

Run: `python3 -m pytest tests/test_velog_publish.py -v`
Expected: 새 테스트들 FAIL (AttributeError: parse_frontmatter 등)

- [ ] **Step 4: 구현 추가** — `velog_publish.py`에 append (임시 엔트리 교체)

```python
WRITE_POST_MUTATION = """
mutation WritePost($input: WritePostInput!) {
  writePost(input: $input) {
    id
    url_slug
  }
}
""".strip()  # Step 1에서 확인한 실제 문자열로 교체 가능


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


def _slug(title):
    s = re.sub(r"[^\w가-힣]+", "-", title.strip()).strip("-").lower()
    return s[:60] or "retro"


def write_post_draft(title, body, tags, thumbnail, tokens):
    payload = {
        "operationName": "WritePost",
        "query": WRITE_POST_MUTATION,
        "variables": {"input": {
            "title": title, "body": body, "tags": tags,
            "is_markdown": True, "is_temp": True, "is_private": False,
            "url_slug": _slug(title), "thumbnail": thumbnail,
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
    print(f"- 확인: https://velog.io/saves")
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_velog_publish.py -v`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add skills/retro-blog/scripts/velog_publish.py tests/test_velog_publish.py
git commit -m "feat: velog WritePost 초안 업로드 + publish CLI (종료 코드 계약, 토큰 회전)"
```

---

### Task 5: `retro` 스킬 (SKILL.md) + 스킬 파일 공통 검증 테스트

**Files:**
- Create: `skills/retro/SKILL.md`
- Test: `tests/test_skill_files.py` (모든 skills/*/SKILL.md를 제네릭 검증 — Task 6·7도 자동 커버)

**Interfaces:**
- Consumes: Task 2의 `parse_transcript.py` CLI
- Produces: `retro/spec.md`(스펙 §6 형식). retro-blog·retro-ppt SKILL.md가 이 파일의 존재와 형식에 의존한다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_skill_files.py`

```python
import re
from pathlib import Path

import pytest

SKILLS = sorted((Path(__file__).resolve().parent.parent / "skills").glob("*/SKILL.md"))


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, f"{path}: frontmatter 없음"
    return dict(
        line.split(":", 1) for line in m.group(1).splitlines() if ":" in line
    ), text


def test_at_least_retro_skill_exists():
    names = [p.parent.name for p in SKILLS]
    assert "retro" in names


@pytest.mark.parametrize("skill_md", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_valid(skill_md):
    meta, _ = _frontmatter(skill_md)
    assert meta.get("name", "").strip() == skill_md.parent.name
    assert len(meta.get("description", "").strip()) > 20


@pytest.mark.parametrize("skill_md", SKILLS, ids=lambda p: p.parent.name)
def test_referenced_local_paths_exist(skill_md):
    _, text = _frontmatter(skill_md)
    for ref in re.findall(r"`((?:scripts|assets|references)/[\w./-]+)`", text):
        assert (skill_md.parent / ref).exists(), f"{skill_md.parent.name}: {ref} 없음"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_skill_files.py -v`
Expected: `test_at_least_retro_skill_exists` FAIL (SKILL.md 없음)

- [ ] **Step 3: `skills/retro/SKILL.md` 작성** (아래 내용 그대로)

````markdown
---
name: retro
description: Claude Code 세션의 시행착오를 회고 스펙(retro/spec.md)으로 증류·갱신한다. "회고 정리", "지금까지 정리해줘", "체크포인트", "retro" 요청 시 사용. retro-blog(velog 글)·retro-ppt(발표 덱)의 선행 단계이며, 세션 중간 재호출로 실시간 중간 정리를 지원한다.
---

# retro — 세션 → 회고 스펙 증류

세션 트랜스크립트(JSONL)에서 시행착오(문제→시도→실패→해결)를 추출해 `retro/spec.md`
(단일 진실 소스)를 만들거나 갱신한다. 블로그와 발표 덱은 이 스펙을 렌더링할 뿐이다.
스크립트 경로는 이 스킬의 base directory 기준이다.

## 절차

1. **초기화**: `retro/` 구조가 없으면 생성한다.
   `mkdir -p retro/archive retro/assets/auto retro/assets/inbox retro/out/blog retro/out/ppt retro/.timeline`
   (retro/가 생기면 이후 세션부터 백업 훅이 이 프로젝트에서 활성화된다.)
2. **재료 선택** — 어떤 세션을 회고할지 사용자에게 확인한다(기본: 현재 세션).
   - 현재 세션(가장 최근 수정된 트랜스크립트):
     `ls -t ~/.claude/projects/$(python3 -c 'import re,os;print(re.sub(r"[^A-Za-z0-9]","-",os.getcwd()))')/*.jsonl | head -3`
   - 백업본: `ls -t retro/archive/*.jsonl`
   - 여러 파일을 함께 넘겨도 된다.
3. **파싱**: `python3 "<skill-dir>/scripts/parse_transcript.py" <파일...> --out retro/.timeline/timeline.md`
   실행 후 결과 파일을 Read로 읽는다. `<!-- ── PART n/m ── -->` 마커가 있으면 순서대로 나눠 읽는다.
4. **증류**: 아래 규칙으로 spec.md를 작성/병합한다.
5. **이미지 큐레이션**: 아래 절차대로 제안하고 사용자 승인 후 반영한다.
6. 완료 보고: spec.md 요약 + "이제 /retro-blog(velog 글) 또는 /retro-ppt(발표 덱)로 내보낼 수 있어요" 안내.

## 증류 규칙

- **남긴다**: 반복 실패, 방향 전환(pivot), 사용자 개입·결정, 예상과 다른 결과, 배운 것.
- **버린다**: 오타 수정, 단순 조회, 한 번에 통과한 루틴 작업.
- 타임라인의 ❌(도구 실패) 표시와 그 직후의 대응이 시행착오의 1차 신호다.
- **톤**: 구조는 체계적으로(문제→시도→해결), 서술은 솔직하게. "완벽하게 설계했다"가 아니라
  "여기서 막혀서 이렇게 돌아갔다"를 남긴다. `## 아쉬운 점` 섹션은 생략 불가.

## spec.md 형식

```markdown
---
title: ""
period: YYYY-MM-DD ~ YYYY-MM-DD
sessions:
  - <재료로 쓴 파일명 또는 세션ID>
audience: 팀원/멘토/블로그 독자
tags: [Claude Code, 회고]
thumbnail: ""
status: draft
updated: YYYY-MM-DD
---

## 한 줄 요약
## 배경 / 목표
## 여정
### 문제 1: <제목>
- 상황:
- 시도 1: … → 실패 (이유)
- 시도 2: … → 해결
- 배운 것:
- 이미지: ![캡션](assets/auto/….png)
### 결정 포인트: <A vs B>
## 결과 / 지표
## 아쉬운 점
## 다음 단계
```

다이어그램이 필요하면 mermaid 코드블록을 본문에 직접 넣는다.
이미지 경로는 retro/ 기준 상대 경로(`assets/...`)로 적는다.

## 체크포인트 병합 (spec.md가 이미 있을 때)

- frontmatter의 `sessions`·`updated`를 갱신하고, 새 재료는 여정에 추가 병합한다.
- 같은 문제의 후속 진행이면 해당 문제 섹션에 이어 쓴다.
- **사람이 수동 편집한 문구는 보존한다.** 병합이 모호하면 사용자에게 확인.

## 이미지 큐레이션

1. `ls -l --time-style=+%Y-%m-%dT%H:%M retro/assets/auto/ retro/assets/inbox/ 2>/dev/null`
2. 파일명의 타임스탬프(우선) 또는 수정 시각을 세션 타임라인과 대조해 후보 구간을 추정한다.
3. 각 이미지를 Read로 직접 열어 내용을 확인하고, 여정의 어느 섹션에 어울리는지 제안한다.
4. **사용자 승인 후** spec.md에 `![캡션](assets/…)`로 기록한다. 캡션 초안도 함께 제안.
5. 매칭되지 않는 이미지는 "미배치 목록"으로 보고하고, 스크린샷 없는 핵심 구간은
   mermaid 다이어그램 초안을 제안한다.

## 자동 캡처 관례

retro/가 있는 프로젝트에서 브라우저 검증 스크린샷을 찍을 때는
`retro/assets/auto/<YYYY-MM-DDTHH-MM-SS>-<설명>.png` 사본을 남긴다.
(프로젝트 CLAUDE.md에 이 관례를 한 줄 적어두면 다른 세션에서도 유지된다.)
````

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_skill_files.py -v`
Expected: 전부 PASS (frontmatter name=retro, scripts/parse_transcript.py 존재)

- [ ] **Step 5: 커밋**

```bash
git add skills/retro/SKILL.md tests/test_skill_files.py
git commit -m "feat: retro 스킬 — 증류 규칙·톤 가이드·체크포인트 병합·이미지 큐레이션"
```

---

### Task 6: `retro-blog` 스킬 (SKILL.md + velog-style.md)

**Files:**
- Create: `skills/retro-blog/SKILL.md`
- Create: `skills/retro-blog/references/velog-style.md`
- Test: 기존 `tests/test_skill_files.py`가 자동 커버

**Interfaces:**
- Consumes: `retro/spec.md`(Task 5 형식), `scripts/velog_publish.py` CLI와 종료 코드(Task 4)
- Produces: `retro/out/blog/YYYY-MM-DD-<slug>.md` (frontmatter: title/tags/thumbnail, 이미지는 MD 파일 기준 상대 경로)

- [ ] **Step 1: `skills/retro-blog/SKILL.md` 작성**

````markdown
---
name: retro-blog
description: retro/spec.md 회고 스펙을 velog 블로그 글로 변환하고 이미지 CDN 업로드 + 임시저장(초안) 업로드까지 수행한다. "블로그로 내보내", "velog에 올려줘", "회고 글 써줘" 요청 시 사용. 스펙이 없으면 먼저 retro 스킬을 실행한다.
---

# retro-blog — 회고 스펙 → velog 초안

## 전제

- `retro/spec.md`가 없으면: "먼저 /retro로 회고 스펙을 만들어야 해요"라고 안내하고 중단.
- 업로드는 항상 **임시저장(초안)** 까지만. 공개 발행 버튼은 사용자가 직접 누른다.

## 절차

1. `retro/spec.md`를 Read → `references/velog-style.md` 가이드에 따라 글을 작성해
   `retro/out/blog/YYYY-MM-DD-<slug>.md`로 저장한다.
   - frontmatter: `title`(필수), `tags`(3~5개 리스트), `thumbnail`(선택)
   - 이미지는 **MD 파일 기준 상대 경로**로 적는다: `../../assets/auto/….png`
2. 초안 전문을 사용자에게 보여주고 승인받는다. 수정 요청은 반영 후 재확인.
3. 업로드 실행:
   `python3 "<skill-dir>/scripts/velog_publish.py" publish "retro/out/blog/<파일>.md" --draft`
4. 성공(종료 코드 0): 출력된 확인 URL(https://velog.io/saves)과 편집 URL을 사용자에게 전달.
5. 실패 폴백(종료 코드별):
   - **2 (토큰 없음/만료)**: 아래 "최초 설정"을 안내하고, 완료되면 3번부터 재시도.
   - **3/4/5 (업로드·API·형식 실패)**: "MD 파일이 `retro/out/blog/`에 있으니 velog 에디터에
     통째로 붙여넣고 이미지를 드래그하면 됩니다"라고 안내한다. 이미지 URL 치환본
     (`*.published.md`)이 생성돼 있으면 그 파일을 붙여넣으라고 안내한다(이미지 재업로드 불필요).

## 최초 설정 (velog 토큰)

1. 브라우저에서 velog.io 로그인 → 개발자도구(F12) → Application → Cookies → `https://velog.io`
2. `access_token`, `refresh_token` 값을 복사
3. 터미널에서 실행: `python3 "<skill-dir>/scripts/velog_publish.py" setup`
   (`~/.config/velog-retro/tokens.json`에 0600 권한으로 저장된다. 토큰은 절대 채팅에 붙여넣지
   않게 하고, 위 명령을 사용자가 직접 실행하도록 안내한다 — `! ` 접두사로 실행 가능.)

## 주의

- velog 비공식 API 사용 — 언제든 변경될 수 있다. 실패해도 MD 폴백이 항상 존재한다.
- 토큰을 로그·대화·커밋에 절대 노출하지 않는다.
````

- [ ] **Step 2: `skills/retro-blog/references/velog-style.md` 작성**

```markdown
# velog 회고 글 스타일 가이드

## 글 구조

1. **서두 훅(1~3문장)**: 무엇을 만들었고 어떤 삽질을 했는지 예고. 결과 이미지가 있으면 바로 아래 배치.
2. **배경 / 목표**: 왜 시작했나, 제약은 무엇이었나. 독자가 모르는 용어는 여기서 한 줄 정의.
3. **여정(본문)**: 문제 단위로 `##`/`###` 제목. 각 문제는 "상황 → 시도(실패 포함) → 해결 → 배운 것" 순서.
   - 실패한 시도도 코드/로그 발췌와 함께 남기고, **왜 안 됐는지**를 반드시 쓴다.
   - 코드블록에는 언어를 지정한다(```python 등). 로그는 핵심 줄만 발췌.
4. **결과**: 스크린샷/지표. 되도록 before/after.
5. **아쉬운 점 & 다음 단계**: 한계를 솔직하게. 다음에 시도할 것.
6. **마무리(1~2문장)**: 같은 문제를 겪을 독자에게 건네는 말.

## 문체

- 1인칭 존댓말("~했습니다", "~더라고요"). 과장 금지, 이모지는 절제(섹션당 최대 1개).
- 문단은 3~4문장 이내로 짧게. "체계적으로 정리하되, 막힌 지점은 숨기지 않는다."
- 제목은 검색을 의식해 구체적으로: "X 하다가 Y에서 막힌 이야기" 형태가 좋다.

## velog 관례

- 태그는 3~5개, 첫 태그는 핵심 기술 키워드.
- 헤딩 계층(`##` → `###`)을 지키면 velog 우측 목차가 깔끔하게 생성된다.
- 이미지 캡션은 이미지 바로 다음 줄에 *기울임*으로.
- 마크다운 이미지 문법은 크기 지정이 안 된다. 크기가 필요하면 `<img src="…" width="600">`.
- 인용구(`>`)는 배운 점·핵심 문장 강조에 사용.

## 이미지 경로 규칙

- 초안 MD는 `retro/out/blog/`에 저장되므로 로컬 이미지는 `../../assets/...` 상대 경로로 적는다.
- velog_publish.py가 업로드 시 CDN URL로 자동 치환한다(원격 URL은 그대로 둠).
```

- [ ] **Step 3: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_skill_files.py -v`
Expected: retro-blog 포함 전부 PASS (frontmatter·참조 경로 검증)

- [ ] **Step 4: 커밋**

```bash
git add skills/retro-blog/
git commit -m "feat: retro-blog 스킬 — velog 스타일 가이드, 초안 업로드 절차, 폴백 정책"
```

---

### Task 7: `retro-ppt` 스킬 (SKILL.md + 덱 템플릿 + 이미지 임베더)

**Files:**
- Create: `skills/retro-ppt/SKILL.md`
- Create: `skills/retro-ppt/assets/deck-template.html`
- Create: `skills/retro-ppt/references/deck-guide.md`
- Create: `skills/retro-ppt/scripts/embed_images.py`
- Test: `tests/test_deck.py`

**Interfaces:**
- Consumes: `retro/spec.md`(Task 5 형식)
- Produces: `retro/out/ppt/YYYY-MM-DD-<slug>.html` (단일 파일 덱). `embed_images.py <html파일>` CLI — 로컬 `<img src>`를 data URI로 인라인(제자리 수정), 누락 이미지는 회색 플레이스홀더로 교체, 2MB 초과는 경고.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_deck.py`

```python
import base64
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "skills" / "retro-ppt" / "assets" / "deck-template.html"
EMBED = ROOT / "skills" / "retro-ppt" / "scripts" / "embed_images.py"

spec = importlib.util.spec_from_file_location("embed_images", EMBED)
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_template_has_required_parts():
    text = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "<!-- SLIDES:START -->", "<!-- SLIDES:END -->",
        "@media print", "keydown", 'class="slide',
        "slide-title", "slide-section", "slide-quote", "slide-end",
    ):
        assert marker in text, f"템플릿에 {marker} 없음"
    assert "http://" not in text and "https://" not in text.replace("https://velog", "")


def test_embed_rewrites_local_img_to_data_uri(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a.png").write_bytes(PNG)
    html = tmp_path / "deck.html"
    html.write_text('<img src="img/a.png"><img src="data:image/png;base64,xx">', encoding="utf-8")
    changed, missing = em.embed(html)
    out = html.read_text(encoding="utf-8")
    assert changed == 1 and missing == 0
    assert 'src="data:image/png;base64,' in out
    assert 'src="img/a.png"' not in out


def test_embed_missing_image_becomes_placeholder(tmp_path):
    html = tmp_path / "deck.html"
    html.write_text('<img src="nope.png" alt="스크린샷">', encoding="utf-8")
    changed, missing = em.embed(html)
    out = html.read_text(encoding="utf-8")
    assert missing == 1
    assert "이미지 없음" in out and 'src="nope.png"' not in out


def test_embed_cli(tmp_path):
    (tmp_path / "a.png").write_bytes(PNG)
    html = tmp_path / "deck.html"
    html.write_text('<img src="a.png">', encoding="utf-8")
    rc = subprocess.run([sys.executable, str(EMBED), str(html)], capture_output=True).returncode
    assert rc == 0
    assert "data:image/png" in html.read_text(encoding="utf-8")
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_deck.py -v`
Expected: 수집 에러 (embed_images.py 없음)

- [ ] **Step 3: `skills/retro-ppt/scripts/embed_images.py` 구현**

```python
#!/usr/bin/env python3
"""단일 파일 덱을 위해 로컬 <img src>를 data URI로 인라인한다(제자리 수정).

- 원격(http/https)·data: URI는 건드리지 않는다.
- 누락 이미지는 회색 플레이스홀더 SVG로 교체하고 경고를 출력한다.
- 2MB 초과 이미지는 경고(리사이즈 제안)하되 임베드는 수행한다.
표준 라이브러리만 사용.
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

BIG = 2 * 1024 * 1024
PLACEHOLDER_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='800' height='450'>"
    "<rect width='100%' height='100%' fill='#333'/>"
    "<text x='50%' y='50%' fill='#999' font-size='28' text-anchor='middle'>이미지 없음</text></svg>"
)
IMG_SRC_RE = re.compile(r'(<img[^>]*?src=")([^"]+)(")', re.IGNORECASE)


def embed(html_path: Path):
    html_path = Path(html_path)
    base = html_path.parent
    changed = missing = 0

    def repl(m):
        nonlocal changed, missing
        src = m.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        local = (base / src).resolve()
        if not local.is_file():
            missing += 1
            print(f"경고: 이미지 없음 → 플레이스홀더 처리: {src}", file=sys.stderr)
            data = base64.b64encode(PLACEHOLDER_SVG.encode()).decode()
            return f"{m.group(1)}data:image/svg+xml;base64,{data}{m.group(3)}"
        raw = local.read_bytes()
        if len(raw) > BIG:
            print(f"경고: {src} {len(raw) // 1024}KB — 리사이즈 권장(임베드는 수행)", file=sys.stderr)
        ctype = mimetypes.guess_type(str(local))[0] or "image/png"
        changed += 1
        return f"{m.group(1)}data:{ctype};base64,{base64.b64encode(raw).decode()}{m.group(3)}"

    text = html_path.read_text(encoding="utf-8")
    html_path.write_text(IMG_SRC_RE.sub(repl, text), encoding="utf-8")
    return changed, missing


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("사용법: embed_images.py <html파일>", file=sys.stderr)
        return 1
    changed, missing = embed(Path(argv[0]))
    print(f"임베드 {changed}개, 플레이스홀더 {missing}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: `skills/retro-ppt/assets/deck-template.html` 작성** (전체 — 외부 요청 0)

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>회고 발표</title>
<style>
  :root { --bg:#111418; --fg:#e8eaed; --dim:#9aa0a6; --accent:#7aa2f7; --card:#1b2027; }
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { height:100%; background:var(--bg); color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Pretendard","Noto Sans KR","Malgun Gothic",sans-serif; }
  #stage { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; }
  .slide { width:1280px; height:720px; padding:72px 88px; display:none; flex-direction:column;
    justify-content:center; gap:28px; transform-origin:center; }
  .slide.active { display:flex; }
  h1 { font-size:64px; line-height:1.2; } h2 { font-size:44px; color:var(--accent); }
  h3 { font-size:32px; } p,li { font-size:28px; line-height:1.55; color:var(--fg); }
  ul { padding-left:1.2em; display:flex; flex-direction:column; gap:14px; }
  .dim { color:var(--dim); font-size:22px; }
  code,pre { font-family:ui-monospace,Consolas,monospace; background:var(--card); border-radius:8px; }
  code { padding:2px 8px; font-size:24px; } pre { padding:20px; font-size:22px; overflow:hidden; }
  img { max-width:100%; max-height:480px; border-radius:12px; }
  .caption { color:var(--dim); font-size:20px; text-align:center; }
  .fail { color:#f7768e; } .ok { color:#9ece6a; }

  .slide-title { align-items:flex-start; } .slide-title h1 { font-size:72px; }
  .slide-section { align-items:center; text-align:center; background:linear-gradient(180deg,var(--bg),#151a21); }
  .slide-image { align-items:center; }
  .slide-two-col .cols { display:grid; grid-template-columns:1fr 1fr; gap:40px; }
  .slide-two-col .col { background:var(--card); border-radius:16px; padding:32px; }
  .slide-quote { align-items:center; text-align:center; }
  .slide-quote blockquote { font-size:40px; line-height:1.5; max-width:1000px; }
  .slide-end { align-items:center; text-align:center; }

  #hud { position:fixed; right:16px; bottom:12px; color:var(--dim); font-size:14px; z-index:9; }
  @media print {
    #hud { display:none; }
    #stage { position:static; display:block; }
    .slide { display:flex !important; transform:none !important; page-break-after:always;
      width:100%; height:100vh; }
  }
</style>
</head>
<body>
<div id="stage">
<!-- SLIDES:START -->
<section class="slide slide-title">
  <p class="dim">2026-07-28 · 회고</p>
  <h1>제목이 들어갈 자리</h1>
  <p class="dim">발표자</p>
</section>
<section class="slide slide-section"><h2>섹션 제목</h2><p class="dim">부제</p></section>
<section class="slide slide-content">
  <h2>내용 슬라이드</h2>
  <ul><li>핵심 1</li><li class="fail">시도 → 실패한 것</li><li class="ok">해결</li></ul>
</section>
<section class="slide slide-image">
  <h2>이미지 슬라이드</h2><img src="" alt=""><p class="caption">캡션</p>
</section>
<section class="slide slide-two-col">
  <h2>비교</h2>
  <div class="cols"><div class="col"><h3>A안</h3><p>…</p></div><div class="col"><h3>B안</h3><p>…</p></div></div>
</section>
<section class="slide slide-quote"><blockquote>"배운 점 한 문장"</blockquote></section>
<section class="slide slide-end"><h1>감사합니다</h1><p class="dim">Q&amp;A</p></section>
<!-- SLIDES:END -->
</div>
<div id="hud"><span id="pos"></span> · ←/→ 이동 · 인쇄(Ctrl+P)로 PDF</div>
<script>
  const slides = [...document.querySelectorAll(".slide")];
  let cur = Math.min(Math.max(parseInt(location.hash.slice(1) || "1", 10) - 1, 0), slides.length - 1);
  function fit() {
    const s = Math.min(innerWidth / 1280, innerHeight / 720) * 0.96;
    slides.forEach(el => el.style.transform = `scale(${s})`);
  }
  function show(i) {
    cur = Math.min(Math.max(i, 0), slides.length - 1);
    slides.forEach((el, k) => el.classList.toggle("active", k === cur));
    document.getElementById("pos").textContent = `${cur + 1} / ${slides.length}`;
    history.replaceState(null, "", "#" + (cur + 1));
  }
  addEventListener("keydown", e => {
    if (["ArrowRight", " ", "PageDown"].includes(e.key)) show(cur + 1);
    else if (["ArrowLeft", "PageUp"].includes(e.key)) show(cur - 1);
    else if (e.key === "Home") show(0);
    else if (e.key === "End") show(slides.length - 1);
  });
  addEventListener("click", e => {
    if (e.clientX > innerWidth / 2) show(cur + 1); else show(cur - 1);
  });
  addEventListener("resize", fit);
  fit(); show(cur);
</script>
</body>
</html>
```

- [ ] **Step 5: `skills/retro-ppt/references/deck-guide.md` 작성**

```markdown
# 회고 발표 덱 구성 가이드

## 서사 (12~20장 권장)

1. 표지(slide-title): 제목·날짜·발표자
2. 한 줄 요약(slide-quote): 이 회고를 한 문장으로
3. 배경/목표(slide-content): 왜 시작했나, 제약 2~3개
4. 문제별 묶음 — 문제마다:
   - 섹션 구분(slide-section): "문제 N: <제목>"
   - 시도와 실패(slide-content): 불릿에 .fail/.ok 클래스로 실패→해결 대비
   - 근거 화면(slide-image) 또는 비교(slide-two-col): A안 vs B안 결정 포인트
5. 배운 점(slide-quote): 문제당 1문장씩 모아서
6. 아쉬운 점 + 다음 단계(slide-content) — 솔직하게, 생략 금지
7. 끝(slide-end)

## 원칙

- 슬라이드당 핵심 1개, 불릿 5개 이하, 한 불릿 한 줄.
- 코드/로그는 핵심 3~6줄만 발췌(pre 사용), 전체는 블로그로 미룬다.
- 발표 톤도 회고 톤과 동일: 체계적 구조 + 솔직한 서술.
- 템플릿의 CSS 클래스만 사용한다(새 스타일 추가 금지 — 단일 파일 무결성 유지).
```

- [ ] **Step 6: `skills/retro-ppt/SKILL.md` 작성**

````markdown
---
name: retro-ppt
description: retro/spec.md 회고 스펙을 발표용 단일 파일 HTML 슬라이드 덱으로 변환한다. "PPT로 만들어", "발표자료로", "슬라이드 뽑아줘" 요청 시 사용. 스펙이 없으면 먼저 retro 스킬을 실행한다. 키보드로 넘기고 인쇄(Ctrl+P)로 PDF화한다.
---

# retro-ppt — 회고 스펙 → HTML 발표 덱

## 전제

`retro/spec.md`가 없으면 "먼저 /retro로 회고 스펙을 만들어야 해요"라고 안내하고 중단.

## 절차

1. `retro/spec.md`를 Read → `references/deck-guide.md`의 서사 구조로 슬라이드를 설계한다.
2. `assets/deck-template.html`을 Read → `<!-- SLIDES:START -->` ~ `<!-- SLIDES:END -->` 사이를
   설계한 슬라이드로 교체해 `retro/out/ppt/YYYY-MM-DD-<slug>.html`로 저장한다.
   - 템플릿의 슬라이드 타입 클래스만 사용: slide-title / slide-section / slide-content /
     slide-image / slide-two-col / slide-quote / slide-end
   - 이미지는 일단 로컬 상대 경로로 참조한다: `../../assets/auto/….png`
3. 임베드: `python3 "<skill-dir>/scripts/embed_images.py" "retro/out/ppt/<파일>.html"`
   - stderr 경고 확인: 2MB 초과는 리사이즈 제안, 누락은 플레이스홀더 처리됨을 사용자에게 알린다.
4. 검증: 가능하면 브라우저(chrome-devtools MCP)로 열어 표지·중간·끝 슬라이드와
   키보드 내비를 확인한다. 불가하면 파일을 열어 SLIDES 마커 사이 구조를 육안 점검.
5. 사용자 안내: 파일 경로, 조작법(←/→ 이동, Ctrl+P → PDF 저장), 슬라이드 수.
````

- [ ] **Step 7: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_deck.py tests/test_skill_files.py -v`
Expected: 전부 PASS

- [ ] **Step 8: 커밋**

```bash
git add skills/retro-ppt/ tests/test_deck.py
git commit -m "feat: retro-ppt 스킬 — 단일 파일 덱 템플릿, data URI 임베더, 서사 가이드"
```

---

### Task 8: 패키징 (`plugin.json`) + 개인 설치 (`install.sh`)

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `install.sh`
- Test: `tests/test_install.sh`

**Interfaces:**
- Consumes: `skills/retro|retro-blog|retro-ppt`, `hooks/archive_transcript.py`
- Produces: `~/.claude/skills/{retro,retro-blog,retro-ppt}` 심링크, `~/.claude/settings.json`의 SessionEnd/PreCompact 훅 항목(절대 경로, 멱등)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_install.sh`

```bash
#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fails=0
t() { if eval "$2" >/dev/null 2>&1; then echo "PASS $1"; else echo "FAIL $1"; fails=$((fails+1)); fi; }
TMP=$(mktemp -d)
export HOME="$TMP"
mkdir -p "$HOME/.claude"
echo '{"model":"keep-me"}' > "$HOME/.claude/settings.json"

bash "$ROOT/install.sh" >/dev/null

t "skill symlinks" "[ -L \"$HOME/.claude/skills/retro\" ] && [ -L \"$HOME/.claude/skills/retro-blog\" ] && [ -L \"$HOME/.claude/skills/retro-ppt\" ]"
t "symlink resolves" "[ -f \"$HOME/.claude/skills/retro/SKILL.md\" ]"
t "hook registered SessionEnd" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));cmds=[h[\"command\"] for e in d[\"hooks\"][\"SessionEnd\"] for h in e[\"hooks\"]];assert any(\"archive_transcript.py\" in c for c in cmds)'"
t "hook registered PreCompact" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));cmds=[h[\"command\"] for e in d[\"hooks\"][\"PreCompact\"] for h in e[\"hooks\"]];assert any(\"archive_transcript.py\" in c for c in cmds)'"
t "existing keys preserved" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));assert d[\"model\"]==\"keep-me\"'"
t "backup created" "ls \"$HOME/.claude/settings.json.bak-\"*"

bash "$ROOT/install.sh" >/dev/null   # 두 번째 실행 — 멱등성
t "idempotent (no dup hooks)" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));cmds=[h[\"command\"] for e in d[\"hooks\"][\"SessionEnd\"] for h in e[\"hooks\"] if \"archive_transcript\" in h[\"command\"]];assert len(cmds)==1,cmds'"

rm -rf "$TMP"
echo "failures: $fails"
exit $fails
```

- [ ] **Step 2: 실패 확인**

Run: `bash tests/test_install.sh`
Expected: FAIL 다수 (install.sh 없음)

- [ ] **Step 3: `.claude-plugin/plugin.json` 작성**

```json
{
  "name": "session-retro",
  "version": "0.1.0",
  "description": "Claude Code 세션의 시행착오를 회고 스펙으로 증류해 velog 블로그 초안과 단일 파일 HTML 발표 덱으로 변환하는 스킬 모음 (retro / retro-blog / retro-ppt + 백업 훅)"
}
```

- [ ] **Step 4: `install.sh` 구현**

```bash
#!/usr/bin/env bash
# session-retro 개인 설치: 스킬 심링크 + settings.json 훅 병합(백업·멱등).
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SKILLS_DIR="${CLAUDE_DIR}/skills"
SETTINGS="${CLAUDE_DIR}/settings.json"

mkdir -p "$SKILLS_DIR"
for name in retro retro-blog retro-ppt; do
  ln -sfn "$REPO/skills/$name" "$SKILLS_DIR/$name"
  echo "스킬 연결: $SKILLS_DIR/$name -> $REPO/skills/$name"
done

REPO="$REPO" SETTINGS="$SETTINGS" python3 - <<'PY'
import json, os, shutil, time
repo = os.environ["REPO"]
settings_path = os.environ["SETTINGS"]
cmd = f'python3 "{repo}/hooks/archive_transcript.py"'
try:
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
except (OSError, json.JSONDecodeError):
    settings = {}
else:
    shutil.copy2(settings_path, f"{settings_path}.bak-{time.strftime('%Y%m%d%H%M%S')}")
hooks = settings.setdefault("hooks", {})
for event in ("SessionEnd", "PreCompact"):
    entries = hooks.setdefault(event, [])
    flat = [h.get("command", "") for e in entries for h in e.get("hooks", [])]
    if not any("archive_transcript.py" in c for c in flat):
        entries.append({"hooks": [{"type": "command", "command": cmd}]})
        print(f"훅 등록: {event}")
    else:
        print(f"훅 이미 등록됨: {event}")
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, ensure_ascii=False, indent=2)
PY

echo "완료. 새 Claude Code 세션에서 /retro 를 사용할 수 있습니다."
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `bash tests/test_install.sh`
Expected: PASS ×7, `failures: 0`

- [ ] **Step 6: 커밋**

```bash
git add .claude-plugin/ install.sh tests/test_install.sh
git commit -m "feat: 플러그인 매니페스트 + 개인 설치 스크립트 (심링크·훅 병합, 백업·멱등)"
```

---

### Task 9: README + 전체 테스트 + 실세션 스모크

**Files:**
- Create: `README.md`
- Test: 전체 스위트 재실행 + 실세션 파서 스모크

**Interfaces:**
- Consumes: 전체
- Produces: 사용자 문서. 이후 도그푸딩(스펙 §10)의 진입점.

- [ ] **Step 1: `README.md` 작성** (아래 골격 그대로, 최신 상태 반영해 완성)

```markdown
# session-retro

Claude Code 세션의 시행착오(문제→시도→실패→해결)를 **회고 스펙**으로 증류해
**velog 블로그 초안**과 **단일 파일 HTML 발표 덱**으로 변환하는 스킬 모음.

## 설치

​```bash
bash install.sh   # 스킬 3개 심링크 + 백업 훅 등록(~/.claude/settings.json, 백업 생성)
​```

## 사용법

| 명령 | 하는 일 |
|---|---|
| `/retro` | 세션 트랜스크립트 → `retro/spec.md` 증류·갱신 (세션 중간 재호출 = 체크포인트) |
| `/retro-blog` | 스펙 → velog 글 초안 → 이미지 CDN 업로드 → **임시저장** 업로드 |
| `/retro-ppt` | 스펙 → 단일 파일 HTML 발표 덱 (←/→ 이동, Ctrl+P로 PDF) |

처음 한 번 `/retro`를 실행하면 프로젝트에 `retro/` 구조가 생기고,
그때부터 세션 종료·컨텍스트 압축 시 트랜스크립트가 `retro/archive/`에 자동 백업된다.

## 이미지 넣기

- 자동: 브라우저 검증 스크린샷을 `retro/assets/auto/<타임스탬프>-<설명>.png`로 저장하는 관례
- 수동: 아무 이미지나 `retro/assets/inbox/`에 던져두면 /retro가 맥락에 맞게 배치를 제안
- 부족한 구간은 mermaid 다이어그램을 제안

## velog 토큰 설정 (최초 1회)

velog.io 로그인 → F12 → Application → Cookies → `access_token`/`refresh_token` 복사 후:
​```bash
python3 skills/retro-blog/scripts/velog_publish.py setup
​```
`~/.config/velog-retro/tokens.json`(0600)에 저장된다. **비공식 API**를 사용하므로
언제든 깨질 수 있고, 깨져도 MD 파일 폴백으로 항상 글을 건질 수 있다.
업로드는 항상 임시저장(초안)까지만 — 공개 발행은 velog에서 직접.

## 권장 설정

트랜스크립트 보존 기간 연장(기본 30일): `~/.claude/settings.json`에 `"cleanupPeriodDays": 90`

## 테스트

​```bash
python3 -m pytest tests/ -v && bash tests/test_hook.sh && bash tests/test_install.sh
​```

## v2 후보

편집 가능 .pptx(PptxGenJS), 공개 발행 자동화, Windows 화면 캡처 셸, 마켓플레이스 배포
```

(코드펜스 안의 `​````는 실제 파일에서는 일반 ``` 로 작성한다.)

- [ ] **Step 2: 전체 테스트 실행**

Run: `python3 -m pytest tests/ -v && bash tests/test_hook.sh && bash tests/test_install.sh`
Expected: 전부 PASS, failures: 0

- [ ] **Step 3: 실세션 스모크(도그푸딩 준비)** — 현재 세션 트랜스크립트로 파서 실행

```bash
proj_dir="$HOME/.claude/projects/$(python3 -c 'import re,os;print(re.sub(r"[^A-Za-z0-9]","-",os.getcwd()))')"
latest="$(ls -t "$proj_dir"/*.jsonl | head -1)"
python3 "skills/retro/scripts/parse_transcript.py" "$latest" --out /tmp/smoke-timeline.md
head -20 /tmp/smoke-timeline.md
```

Expected: exit 0, 타임라인 헤더·통계 출력. (전체 도그푸딩 — /retro → /retro-blog → /retro-ppt — 은 설치 후 스펙 §10 수용 기준대로 별도 수행)

- [ ] **Step 4: 커밋**

```bash
git add README.md
git commit -m "docs: README — 설치·사용법·토큰 설정·보존 기간 권장"
```

---

## Self-Review 결과

- **스펙 커버리지**: §5 구조(Task 1~8), §6 spec.md 계약(Task 5), §7.1 훅(Task 1), §7.2 파서·큐레이션(Task 2·5), §7.3 velog(Task 3·4·6), §7.4 덱(Task 7), §8 에러 정책(각 태스크의 exit 코드·폴백·플레이스홀더), §9 테스트(전 태스크 TDD), §10 도그푸딩(Task 9 스모크 + 설치 후 별도), 설치(§5.1, Task 8). 갭 없음.
- **플레이스홀더 스캔**: 코드 블록 전부 실행 가능한 실코드. SKILL.md·가이드 전문 포함. 통과.
- **타입/이름 일관성**: `_http` 시그니처(Task 3 정의 ↔ Task 4 사용), 종료 코드 0/2/3/4/5(Task 4 정의 ↔ Task 6 SKILL.md 폴백 분기), `SLIDES:START/END` 마커(Task 7 템플릿 ↔ SKILL.md ↔ 테스트), `retro/` 경로 규칙(전 태스크) 일치 확인.
```
