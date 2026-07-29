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
t "nudge registered SessionStart" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));cmds=[h[\"command\"] for e in d[\"hooks\"][\"SessionStart\"] for h in e[\"hooks\"]];assert any(\"retro_nudge.py\" in c for c in cmds)'"
t "existing keys preserved" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));assert d[\"model\"]==\"keep-me\"'"
t "backup created" "ls \"$HOME/.claude/settings.json.bak-\"*"

bash "$ROOT/install.sh" >/dev/null   # 두 번째 실행 — 멱등성
t "idempotent (no dup hooks)" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));cmds=[h[\"command\"] for e in d[\"hooks\"][\"SessionEnd\"] for h in e[\"hooks\"] if \"archive_transcript\" in h[\"command\"]];assert len(cmds)==1,cmds'"
t "idempotent nudge" "python3 -c 'import json,os;d=json.load(open(os.environ[\"HOME\"]+\"/.claude/settings.json\"));cmds=[h[\"command\"] for e in d[\"hooks\"][\"SessionStart\"] for h in e[\"hooks\"] if \"retro_nudge\" in h[\"command\"]];assert len(cmds)==1,cmds'"

rm -rf "$TMP"
echo "failures: $fails"
exit $fails
