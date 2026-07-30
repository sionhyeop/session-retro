#!/usr/bin/env python3
"""진화 스냅샷: 핵심 HTML 산출물(콘텐츠 맵·덱·랜딩 등)의 버전을 보존한다.

구조·디자인이 의미 있게 바뀔 때 실행하면 retro/snapshots/<이름>/에
HTML(용량 5MB 이하일 때)과 스크린샷 PNG를 함께 남긴다 — 나중에 회고에서
"이 산출물이 어떻게 진화했는지"를 이미지 시리즈로 바로 보여줄 수 있다.
표준 라이브러리만 사용. 사용법: snapshot.py <html파일> <라벨> [--retro-dir retro]
"""
import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from html_shot import shot  # noqa: E402

HTML_LIMIT = 5 * 1024 * 1024  # HTML 보존 상한 — 이보다 크면 PNG만 남긴다


def main(argv=None):
    ap = argparse.ArgumentParser(description="HTML 산출물 진화 스냅샷")
    ap.add_argument("html")
    ap.add_argument("label", help="무엇이 바뀌었나 (예: '연대기 축으로 개편')")
    ap.add_argument("--retro-dir", default="retro")
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=800)
    args = ap.parse_args(argv)

    src = Path(args.html)
    if not src.is_file():
        print(f"에러: 파일 없음 — {src}", file=sys.stderr)
        return 1
    label = re.sub(r"[^\w가-힣.-]+", "-", args.label.strip()).strip("-") or "snapshot"
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    dest_dir = Path(args.retro_dir) / "snapshots" / src.stem
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = dest_dir / f"{ts}-{label}"

    if src.stat().st_size <= HTML_LIMIT:
        shutil.copy2(src, base.with_suffix(".html"))
        print(f"보존됨: {base.with_suffix('.html')}")
    else:
        print(f"경고: HTML {src.stat().st_size // 1024}KB > 5MB — PNG만 남깁니다", file=sys.stderr)

    try:
        shot(src, base.with_suffix(".png"), width=args.width, height=args.height)
        print(f"보존됨: {base.with_suffix('.png')}")
    except Exception as e:  # noqa: BLE001 — PNG는 best-effort, HTML 보존이 우선
        print(f"경고: 스크린샷 실패({e}) — HTML만 보존됨", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
