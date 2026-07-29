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
    assert nxt["kind"] == "episode" and "배포 자동화" in nxt["title"]


def test_parse_period():
    import datetime
    assert bm.parse_period("2026-07-01 ~ 2026-07-05") == (
        datetime.date(2026, 7, 1), datetime.date(2026, 7, 5))
    assert bm.parse_period("") is None


def _day(iso, sessions=1, commits=0):
    import datetime
    return {"date": datetime.date.fromisoformat(iso), "sessions": ["세션 제목"] * sessions,
            "turns": sessions * 3, "errors": 0, "commits": commits}


def test_assign_days_coverage_and_uncovered_run():
    import datetime
    days = [_day("2026-07-01"), _day("2026-07-02"), _day("2026-07-05", sessions=3, commits=4)]
    ep = {"slug": "a", "title": "에피소드A", "period": "", "updated": "",
          "dates": (datetime.date(2026, 7, 1), datetime.date(2026, 7, 2)),
          "problems": [], "gaps": [], "images": 0, "stage": "published_public",
          "deck": False, "url": ""}
    bm.assign_days(days, [ep])
    assert days[0]["episode"] is ep and days[1]["episode"] is ep
    assert days[2]["episode"] is None  # 미작성 구간
    cov = bm.coverage(days)
    assert (cov["total"], cov["covered"], cov["published"]) == (3, 2, 2)
    runs = bm.uncovered_runs(days)
    assert len(runs) == 1 and runs[0][0]["date"].day == 5
    nxt = bm.next_suggestion([ep], days)
    assert nxt["kind"] == "uncovered"  # 미작성 구간이 최우선 글감


def test_render_html_shows_uncovered_and_coverage(tmp_path):
    import datetime
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    (retro / "assets" / "inbox" / "x.png").write_bytes(b"i")
    eps = bm.collect(retro)
    days = bm.assign_days([_day("2026-07-10"), _day("2026-07-20", sessions=2)], eps)
    html = bm.render_html(eps, days, bm.assets_summary(retro), "테스트프로젝트")
    assert "인증 삽질기" in html and "stage-spec" in html
    assert "미작성 구간" in html and "50%" in html  # 커버리지 인사이트
    assert "⚠️" in html  # 이미지 부족 배지
    for line in html.splitlines():
        assert not (("http://" in line or "https://" in line) and "velog.io" not in line and "xmlns" not in line)


def test_parse_backlog(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "plan.md").write_text(
        "# 콘텐츠 백로그\n\n| 가제 | 훅(한 줄) | 근거 | 태그 |\n|---|---|---|---|\n"
        "| pptx 개발기 | HTML 덱을 넘어 | v2 계획 | ClaudeCode |\n"
        "| 소급 모드 실전기 | 583세션을 지도로 | web-template2 | 회고 |\n", encoding="utf-8")
    items = bm.parse_backlog(retro)
    assert len(items) == 2
    assert items[0]["title"] == "pptx 개발기" and items[0]["hook"] == "HTML 덱을 넘어"
    assert items[1]["basis"] == "web-template2"


def test_backlog_renders_with_copy_bridge(tmp_path):
    retro = make_retro(tmp_path)
    backlog = [{"title": "pptx 개발기", "hook": "훅 문구", "basis": "v2", "tags": ""}]
    html = bm.render_html([], [], bm.assets_summary(retro), "p", backlog=backlog)
    assert "pptx 개발기" in html and "훅 문구" in html
    assert 'data-cmd="' in html and "이어서" in html and "clipboard" in html  # 클릭→복사 브리지
    assert "회고 스펙을 만들어줘" in html  # planned 단계의 다음 액션 지시문
    nxt = bm.next_suggestion([], [], backlog)
    assert nxt["kind"] == "backlog" and nxt["title"] == "pptx 개발기"


def test_parse_story(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "story.md").write_text(
        "# 프로젝트 연대기\n\n| 기간 | 챕터 | 요약 | 글 |\n|---|---|---|---|\n"
        "| 07-01~07-05 | 초기 기능 구축 | 인증·DB 설계 | auth |\n"
        "| 07-06~07-12 | 성능 개선 | 캐시 도입 |  |\n", encoding="utf-8")
    chapters = bm.parse_story(retro)
    assert len(chapters) == 2
    assert chapters[0]["title"] == "초기 기능 구축" and chapters[0]["slug"] == "auth"
    assert chapters[1]["slug"] == ""


def test_story_chapter_view_and_grouped_publish_badge(tmp_path):
    retro = make_retro(tmp_path)
    ep = {"slug": "auth", "title": "인증 삽질기", "period": "", "dates": None, "updated": "",
          "problems": [], "gaps": [], "images": 0, "stage": "published_private",
          "deck": False, "url": "https://velog.io/@u/s"}
    chapters = [
        {"period": "07-01~05", "title": "초기 기능 구축", "summary": "인증·DB", "slug": "auth"},
        {"period": "07-06~12", "title": "성능 개선", "summary": "캐시", "slug": ""},
    ]
    cov = bm.story_coverage(chapters, [ep])
    assert (cov["total"], cov["covered"], cov["published"]) == (2, 1, 1)
    html = bm.render_html([ep], [], bm.assets_summary(retro), "p", story=chapters)
    assert "프로젝트 연대기" in html and "초기 기능 구축" in html
    assert "발행 · 비공개" in html  # 비공개·공개가 '발행' 한 묶음으로 표기
    assert "✍️ 미작성" in html and "성능 개선" in html
    assert "파트의 회고 스펙을 만들어줘" in html  # 미작성 챕터 → 지시문 브리지 (따옴표는 속성 이스케이프됨)
    nxt = bm.next_suggestion([ep], [], [], chapters)
    assert nxt["kind"] == "chapter" and nxt["title"] == "성능 개선"  # 미작성 챕터가 최우선 글감


def test_cli_writes_map(tmp_path):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    out = retro / "map.html"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--retro-dir", str(retro), "--out", str(out)],
        capture_output=True, text=True, cwd=str(tmp_path),
    ).returncode
    assert rc == 0 and "콘텐츠 맵" in out.read_text(encoding="utf-8")


def test_auto_open_only_on_state_change(tmp_path, monkeypatch):
    retro = make_retro(tmp_path)
    (retro / "specs" / "2026-07-10-auth.md").write_text(SPEC_MD, encoding="utf-8")
    opened = []
    monkeypatch.setattr(bm, "_open_browser", lambda p: opened.append(str(p)))
    monkeypatch.setattr(bm, "collect_timeline", lambda **k: [])
    bm.main(["--retro-dir", str(retro), "--open", "auto"])
    assert len(opened) == 1  # 최초 생성 = 변화로 간주
    bm.main(["--retro-dir", str(retro), "--open", "auto"])
    assert len(opened) == 1  # 상태 그대로 → 안 연다
    blog = retro / "out" / "blog" / "2026-07-12-auth.md"
    blog.write_text("---\ntitle: 인증 삽질기\n---\n본문", encoding="utf-8")
    bm.main(["--retro-dir", str(retro), "--open", "auto"])
    assert len(opened) == 2  # spec → draft 로 상태 변화 → 연다
    bm.main(["--retro-dir", str(retro), "--open", "always"])
    assert len(opened) == 3  # always는 무조건


def test_cli_no_retro_dir_exit_1(tmp_path):
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--retro-dir", str(tmp_path / "nope")],
        capture_output=True, text=True, cwd=str(tmp_path),
    ).returncode
    assert rc == 1
