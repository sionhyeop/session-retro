import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro" / "scripts" / "build_map.py"

spec = importlib.util.spec_from_file_location("build_map", SCRIPT)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)

SPEC_MD = """---
title: "인증 삽질기"
period: 2026-07-10 ~ 2026-07-12
tags: [Claude Code, 회고]
status: draft
updated: 2026-07-12
---

## 여정
### 문제 1: 로그인 실패
- 상황: …
- 이미지: ![로그인 화면](assets/auto/login.png)
### 문제 2: 세션 만료
- 상황: 이미지가 없다
"""


def make_retro(tmp_path):
    retro = tmp_path / "retro"
    for d in ("specs", "out/blog", "out/ppt", "assets/auto", "assets/inbox"):
        (retro / d).mkdir(parents=True)
    return retro


def test_spec_only_is_stage_spec(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    eps = bm.collect(retro)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["slug"] == "auth" and ep["title"] == "인증 삽질기"
    assert ep["stage"] == "spec"


def test_stage_progression_draft_private_public(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    blog = retro / "out" / "blog" / "2026-07-12-auth.md"
    blog.write_text("---\ntitle: 인증 삽질기\n---\n본문", encoding="utf-8")
    assert bm.collect(retro)[0]["stage"] == "draft"
    sidecar = blog.with_suffix(".velog.json")
    sidecar.write_text(json.dumps({"id": "p", "url_slug": "s", "username": "u",
                                   "visibility": "private"}), encoding="utf-8")
    assert bm.collect(retro)[0]["stage"] == "published_private"
    sidecar.write_text(json.dumps({"id": "p", "url_slug": "s", "username": "u",
                                   "visibility": "public"}), encoding="utf-8")
    ep = bm.collect(retro)[0]
    assert ep["stage"] == "published_public"
    assert "velog.io/@u/s" in ep["url"]


def test_image_gap_detection(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    ep = bm.collect(retro)[0]
    assert ep["images"] == 1
    assert ep["gaps"] == ["문제 2: 세션 만료"]


def test_deck_badge_and_planned_from_overview(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    (retro / "out" / "ppt" / "2026-07-12-auth.html").write_text("<html>", encoding="utf-8")
    (retro / "overview.md").write_text(
        "## 에피소드 목차\n- 인증 삽질기 — 완료\n- 배포 자동화 — 계획\n", encoding="utf-8")
    eps = bm.collect(retro)
    auth = next(e for e in eps if e["slug"] == "auth")
    assert auth["deck"] is True
    planned = [e for e in eps if e["stage"] == "planned"]
    assert len(planned) == 1 and "배포 자동화" in planned[0]["title"]


def test_next_suggestion_prefers_least_progressed(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    (retro / "overview.md").write_text("## 에피소드 목차\n- 배포 자동화\n", encoding="utf-8")
    eps = bm.collect(retro)
    nxt = bm.next_suggestion(eps)
    assert "배포 자동화" in nxt["title"]


def test_render_html_self_contained(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    (retro / "assets" / "inbox" / "x.png").write_bytes(b"i")
    eps = bm.collect(retro)
    html = bm.render_html(eps, bm.assets_summary(retro), "테스트프로젝트")
    assert "인증 삽질기" in html and "stage-spec" in html
    assert "⚠️" in html  # 이미지 부족 배지
    for line in html.splitlines():
        assert not (("http://" in line or "https://" in line) and "velog.io" not in line and "xmlns" not in line)


def test_cli_writes_map(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    out = retro / "map.html"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--retro-dir", str(retro), "--out", str(out)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 0 and "콘텐츠 맵" in out.read_text(encoding="utf-8")


def test_cli_no_retro_dir_exit_1(tmp_path):
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--retro-dir", str(tmp_path / "nope")],
        capture_output=True, text=True,
    ).returncode
    assert rc == 1
