#!/usr/bin/env python3
"""HTML 파일을 PNG로 렌더링한다 — 블로그 이미지 파이프라인의 핵심 도구.

WSL에서는 Windows의 Chrome/Edge를 headless로 호출한다(실검증됨). 리눅스 크롬도 지원.
콘텐츠 맵·덱 슬라이드·코드 카드·스탯 카드 등 "시각적으로 볼 수 있는 HTML"을
블로그용 이미지로 만들 때 쓴다. 표준 라이브러리만 사용.

사용법: html_shot.py <html파일> <out.png> [--width 1280] [--height 800]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS_BROWSERS = [
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
]
LINUX_BROWSERS = ["google-chrome", "chromium-browser", "chromium"]


def find_browser():
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).is_file():
        return env
    for p in WINDOWS_BROWSERS:
        if Path(p).is_file():
            return p
    for name in LINUX_BROWSERS:
        p = shutil.which(name)
        if p:
            return p
    return None


def _win_path(path):
    return subprocess.run(
        ["wslpath", "-w", str(path)], capture_output=True, text=True, check=True,
    ).stdout.strip()


def shot(html_path, out_png, width=1280, height=800, browser=None):
    browser = browser or find_browser()
    if not browser:
        raise RuntimeError("Chrome/Edge를 찾지 못했습니다 (환경변수 CHROME_PATH로 지정 가능)")
    html_path = Path(html_path).resolve()
    out_png = Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    is_windows_exe = str(browser).endswith(".exe")
    url = f"file:///{_win_path(html_path)}" if is_windows_exe else html_path.as_uri()
    out_arg = _win_path(out_png) if is_windows_exe else str(out_png)
    result = subprocess.run(
        [browser, "--headless=new", "--disable-gpu",
         f"--window-size={width},{height}", f"--screenshot={out_arg}", url],
        capture_output=True, text=True, timeout=90,
    )
    if not out_png.is_file() or out_png.stat().st_size == 0:
        raise RuntimeError(f"스크린샷 실패: {result.stderr.strip()[:200]}")
    return out_png


def main(argv=None):
    ap = argparse.ArgumentParser(description="HTML → PNG 스크린샷")
    ap.add_argument("html")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    args = ap.parse_args(argv)
    try:
        out = shot(args.html, args.out, width=args.width, height=args.height)
    except (RuntimeError, subprocess.SubprocessError) as e:
        print(f"에러: {e}", file=sys.stderr)
        return 1
    print(f"작성됨: {out} ({out.stat().st_size:,}B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
