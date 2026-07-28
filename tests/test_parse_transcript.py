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
