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
