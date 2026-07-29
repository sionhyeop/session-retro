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
