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
        if not isinstance(obj, dict):
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
        if not isinstance(message, dict):
            continue
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
