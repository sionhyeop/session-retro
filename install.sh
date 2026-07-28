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
