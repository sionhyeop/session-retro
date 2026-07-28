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


def embed(html_path):
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
