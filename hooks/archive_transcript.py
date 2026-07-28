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
    data = {}
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
