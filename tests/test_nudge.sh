#!/usr/bin/env bash
# 주의: 훅 출력($out)을 eval로 통과시키면 문구 속 괄호·따옴표가 bash 문법을 깨뜨린다.
# 반드시 파일로 받아서 검사한다 (실제로 겪은 테스트 하네스 버그).
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
json "$TMP/proj" startup | python3 "$HOOK" > "$TMP/out_a.json"
t "fresh material nudges checkpoint" "grep -q '체크포인트' \"$TMP/out_a.json\""
t "output is valid hook json" "python3 -c \"import json;d=json.load(open('$TMP/out_a.json'));assert d['hookSpecificOutput']['hookEventName']=='SessionStart'\""

# B) compact 재시작 → 침묵
json "$TMP/proj" compact | python3 "$HOOK" > "$TMP/out_b.txt"
t "compact is silent" "[ ! -s \"$TMP/out_b.txt\" ]"

# C) 미활성 + 세션 3개 → 소급 안내
mkdir -p "$TMP/proj2"
MUNGED=$(python3 -c "import re;print(re.sub(r'[^A-Za-z0-9]','-','$TMP/proj2'))")
mkdir -p "$TMP/.claude/projects/$MUNGED"
for i in 1 2 3; do echo x > "$TMP/.claude/projects/$MUNGED/s$i.jsonl"; done
json "$TMP/proj2" startup | python3 "$HOOK" > "$TMP/out_c.json"
t "inactive project suggests backfill" "grep -q '소급' \"$TMP/out_c.json\""

# D) 해당 없음 → 무출력, exit 0
mkdir -p "$TMP/proj3"
json "$TMP/proj3" startup | python3 "$HOOK" > "$TMP/out_d.txt"; rc=$?
t "nothing to say is silent exit 0" "[ ! -s \"$TMP/out_d.txt\" ] && [ $rc -eq 0 ]"

# F) map-actions.json 존재 → 스테이징 반영 지시
mkdir -p "$TMP/proj4/retro"
echo '{"actions":[]}' > "$TMP/proj4/retro/map-actions.json"
json "$TMP/proj4" startup | python3 "$HOOK" > "$TMP/out_f.json"
t "staged actions file triggers processing" "grep -q 'map-actions' \"$TMP/out_f.json\""

# E) 쓰레기 입력 → exit 0
echo garbage | python3 "$HOOK" >/dev/null; rc=$?
t "garbage exit 0" "[ $rc -eq 0 ]"

rm -rf "$TMP"
echo "failures: $fails"
exit $fails
