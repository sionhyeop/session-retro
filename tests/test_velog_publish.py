import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro-blog" / "scripts" / "velog_publish.py"

spec = importlib.util.spec_from_file_location("velog_publish", SCRIPT)
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "TOKEN_PATH", tmp_path / "cfg" / "tokens.json")
    return tmp_path


def test_setup_writes_tokens_0600(home, monkeypatch):
    answers = iter(["at-123", "rt-456"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert vp.cmd_setup() == 0
    saved = json.loads(vp.TOKEN_PATH.read_text())
    assert saved == {"access_token": "at-123", "refresh_token": "rt-456"}
    assert stat.S_IMODE(vp.TOKEN_PATH.stat().st_mode) == 0o600


def test_cookie_header(home):
    hdr = vp.cookie_header({"access_token": "a", "refresh_token": "r"})
    assert "access_token=a" in hdr and "refresh_token=r" in hdr


def test_upload_image_returns_cdn_url(home, tmp_path, monkeypatch):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG fake")
    calls = {}

    def fake_http(url, method="GET", headers=None, data=None):
        calls["url"], calls["headers"], calls["data"] = url, headers, data
        return 200, [], json.dumps({"path": "https://velog.velcdn.com/images/u/x.png"}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    url = vp.upload_image(img, {"access_token": "a", "refresh_token": "r"})
    assert url == "https://velog.velcdn.com/images/u/x.png"
    assert calls["url"] == vp.UPLOAD_URL
    ctype = dict(calls["headers"])["Content-Type"]
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="image"' in calls["data"] and b'name="type"' in calls["data"] and b"post" in calls["data"]
    assert "Cookie" in dict(calls["headers"])


def test_rewrite_images_uploads_local_and_skips_remote(home, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.png").write_bytes(b"img")
    md = "![캡션](assets/a.png)\n![원격](https://example.com/b.png)\n"
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/a.png")
    new_md, n = vp.rewrite_images(md, tmp_path, {"access_token": "a"})
    assert n == 1
    assert "https://velog.velcdn.com/u/a.png" in new_md
    assert "https://example.com/b.png" in new_md


def test_rewrite_images_uses_cache_and_uploads_only_new(home, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "old.png").write_bytes(b"img")
    (tmp_path / "assets" / "new.png").write_bytes(b"img")
    uploaded = []

    def fake_upload(p, t):
        uploaded.append(p.name)
        return f"https://velog.velcdn.com/u/{p.name}"

    monkeypatch.setattr(vp, "upload_image", fake_upload)
    cache = {"assets/old.png": "https://velog.velcdn.com/u/cached-old.png"}
    md = "![a](assets/old.png)\n![b](assets/new.png)"
    new_md, n = vp.rewrite_images(md, tmp_path, {"access_token": "a"}, cache=cache)
    assert uploaded == ["new.png"]  # 캐시된 이미지는 재업로드하지 않는다
    assert "cached-old.png" in new_md and "u/new.png" in new_md
    assert cache["assets/new.png"] == "https://velog.velcdn.com/u/new.png"  # 캐시 갱신


def test_upload_http_error_raises(home, tmp_path, monkeypatch):
    img = tmp_path / "x.png"
    img.write_bytes(b"img")
    monkeypatch.setattr(vp, "_http", lambda *a, **k: (500, [], b"boom"))
    with pytest.raises(vp.VelogError):
        vp.upload_image(img, {"access_token": "a"})


MD = """---
title: 테스트 회고
tags: [Claude Code, 회고]
---

본문입니다.

![스크린샷](assets/a.png)
"""


def test_parse_frontmatter():
    meta, body = vp.parse_frontmatter(MD)
    assert meta["title"] == "테스트 회고"
    assert meta["tags"] == ["Claude Code", "회고"]
    assert body.startswith("본문입니다.")


def test_parse_frontmatter_missing_title():
    meta, _ = vp.parse_frontmatter("---\ntags: []\n---\n본문")
    assert "title" not in meta


def test_write_post_draft_mode_payload(home, monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["url"], captured["data"] = url, json.loads(data)
        return 200, [], json.dumps({"data": {"writePost": {"id": "p-1", "url_slug": "slug"}}}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    result = vp.write_post("제목", "본문", ["a"], None, {"access_token": "a", "refresh_token": "r"},
                           temp=True, private=False)
    assert result["id"] == "p-1"
    assert captured["url"] == vp.GRAPHQL_URL
    inp = captured["data"]["variables"]["input"]
    assert inp["is_temp"] is True and inp["is_markdown"] is True
    assert inp["title"] == "제목" and inp["tags"] == ["a"]
    assert inp["meta"] == {}  # 레퍼런스 구현(velog-mcp) 확인 결과 필수 필드


def test_write_post_default_is_private_publish(home, monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["data"] = json.loads(data)
        return 200, [], json.dumps({"data": {"writePost": {"id": "p", "url_slug": "s"}}}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    vp.write_post("t", "b", [], None, {"access_token": "a"})
    inp = captured["data"]["variables"]["input"]
    assert inp["is_temp"] is False and inp["is_private"] is True  # 기본값 = 비공개 발행


def test_write_post_graphql_error_raises(home, monkeypatch):
    monkeypatch.setattr(
        vp, "_http",
        lambda *a, **k: (200, [], json.dumps({"errors": [{"message": "nope"}]}).encode()),
    )
    with pytest.raises(vp.VelogError):
        vp.write_post("t", "b", [], None, {"access_token": "a"})


def test_edit_post_payload(home, monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["data"] = json.loads(data)
        return 200, [], json.dumps({"data": {"editPost": {"id": "p-1", "url_slug": "s"}}}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    vp.edit_post("p-1", "제목", "본문", ["a"], None, "slug",
                 {"access_token": "a"}, private=False)
    inp = captured["data"]["variables"]["input"]
    assert inp["id"] == "p-1" and inp["is_private"] is False and inp["is_temp"] is False
    assert inp["url_slug"] == "slug" and inp["meta"] == {}


def test_token_rotation_persisted(home, monkeypatch):
    vp.save_tokens({"access_token": "old", "refresh_token": "r"})

    def fake_http(url, method="GET", headers=None, data=None):
        return 200, [("Set-Cookie", "access_token=new; Path=/; HttpOnly")], json.dumps(
            {"data": {"writePost": {"id": "p", "url_slug": "s"}}}
        ).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    tokens = vp.load_tokens()
    vp.write_post("t", "b", [], None, tokens)
    assert vp.load_tokens()["access_token"] == "new"


def test_cmd_publish_end_to_end_writes_sidecar(home, tmp_path, monkeypatch):
    blog = tmp_path / "out" / "blog"
    blog.mkdir(parents=True)
    (blog / "post.md").write_text(MD, encoding="utf-8")
    assets = blog / "assets"
    assets.mkdir()
    (assets / "a.png").write_bytes(b"img")
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/a.png")
    monkeypatch.setattr(
        vp, "write_post",
        lambda *a, **k: {"id": "p-9", "url_slug": "s", "user": {"username": "mico"}},
    )
    rc = vp.cmd_publish(str(blog / "post.md"))
    assert rc == 0
    published = (blog / "post.published.md").read_text(encoding="utf-8")
    assert "velcdn.com" in published
    sidecar = json.loads((blog / "post.velog.json").read_text(encoding="utf-8"))
    assert sidecar["id"] == "p-9" and sidecar["visibility"] == "private"
    assert sidecar["username"] == "mico"


def test_cmd_publish_mode_flags(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD.replace("![스크린샷](assets/a.png)", ""), encoding="utf-8")
    captured = {}

    def fake_write(title, body, tags, thumbnail, tokens, temp=False, private=True, series_id=None):
        captured.update(temp=temp, private=private)
        return {"id": "p", "url_slug": "s", "user": {"username": "u"}}

    monkeypatch.setattr(vp, "write_post", fake_write)
    assert vp.cmd_publish(str(md)) == 0
    assert captured == {"temp": False, "private": True}   # 기본 = 비공개 발행
    assert vp.cmd_publish(str(md), mode="public") == 0
    assert captured == {"temp": False, "private": False}
    assert vp.cmd_publish(str(md), mode="draft") == 0
    assert captured == {"temp": True, "private": False}


def test_cmd_visibility_public(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD, encoding="utf-8")
    (tmp_path / "p.published.md").write_text("---\ntitle: 테스트 회고\n---\n\n본문", encoding="utf-8")
    (tmp_path / "p.velog.json").write_text(json.dumps({
        "id": "p-1", "url_slug": "s", "username": "u", "title": "테스트 회고",
        "tags": ["테스트"], "thumbnail": None, "visibility": "private",
    }), encoding="utf-8")
    captured = {}

    def fake_edit(post_id, title, body, tags, thumbnail, url_slug, tokens, temp=False, private=True):
        captured.update(post_id=post_id, private=private, title=title)
        return {"id": post_id, "url_slug": url_slug}

    monkeypatch.setattr(vp, "edit_post", fake_edit)
    assert vp.cmd_visibility(str(md), public=True) == 0
    assert captured["post_id"] == "p-1" and captured["private"] is False
    sidecar = json.loads((tmp_path / "p.velog.json").read_text(encoding="utf-8"))
    assert sidecar["visibility"] == "public"


def test_cmd_visibility_missing_sidecar_exit_5(home, tmp_path):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD, encoding="utf-8")
    assert vp.cmd_visibility(str(md), public=True) == 5


# ── v1.5: 썸네일·시리즈·수정 동기화·mermaid ──────────────────────────

def test_first_image_url():
    md = "텍스트\n![a](https://velog.velcdn.com/u/a.png)\n![b](https://velog.velcdn.com/u/b.png)"
    assert vp.first_image_url(md) == "https://velog.velcdn.com/u/a.png"
    assert vp.first_image_url("이미지 없음") is None


def test_write_post_series_id(home, monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["data"] = json.loads(data)
        return 200, [], json.dumps({"data": {"writePost": {"id": "p", "url_slug": "s"}}}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    vp.write_post("t", "b", [], None, {"access_token": "a"}, series_id="s-1")
    assert captured["data"]["variables"]["input"]["series_id"] == "s-1"


def test_fetch_series_uses_v2(home, monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["url"], captured["data"] = url, json.loads(data)
        return 200, [], json.dumps({"data": {"seriesList": [
            {"id": "s1", "name": "회고 시리즈", "posts_count": 3},
        ]}}).encode()

    monkeypatch.setattr(vp, "_http", fake_http)
    series = vp.fetch_series("mico")
    assert captured["url"] == vp.V2_GRAPHQL
    assert series[0]["name"] == "회고 시리즈"


def test_cmd_publish_auto_thumbnail_and_series(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    blog = tmp_path / "p.md"
    blog.write_text(MD, encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.png").write_bytes(b"img")
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/a.png")
    captured = {}

    def fake_write(title, body, tags, thumbnail, tokens, temp=False, private=True, series_id=None):
        captured.update(thumbnail=thumbnail, series_id=series_id)
        return {"id": "p", "url_slug": "s", "user": {"username": "u"}}

    monkeypatch.setattr(vp, "write_post", fake_write)
    assert vp.cmd_publish(str(blog), series_id="s-9") == 0
    assert captured["thumbnail"] == "https://velog.velcdn.com/u/a.png"  # 본문 첫 이미지 자동 지정
    assert captured["series_id"] == "s-9"
    sidecar = json.loads(blog.with_suffix(".velog.json").read_text(encoding="utf-8"))
    assert sidecar["series_id"] == "s-9"


def test_convert_mermaid_replaces_block(home, tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "_http", lambda *a, **k: (200, [], b"\x89PNGfake"))
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/d.png")
    md = "앞\n\n```mermaid\ngraph TD; A-->B\n```\n\n뒤"
    new_md, n = vp.convert_mermaid(md, {"access_token": "a"})
    assert n == 1
    assert "```mermaid" not in new_md
    assert "![다이어그램](https://velog.velcdn.com/u/d.png)" in new_md


def test_convert_mermaid_failure_keeps_block(home, monkeypatch):
    monkeypatch.setattr(vp, "_http", lambda *a, **k: (500, [], b"boom"))
    md = "```mermaid\ngraph TD; A-->B\n```"
    new_md, n = vp.convert_mermaid(md, {"access_token": "a"})
    assert n == 0 and "```mermaid" in new_md


def test_convert_mermaid_cache_skips_rerender(home, monkeypatch):
    calls = []
    monkeypatch.setattr(vp, "_http", lambda *a, **k: calls.append(1) or (200, [], b"png"))
    monkeypatch.setattr(vp, "upload_image", lambda p, t: "https://velog.velcdn.com/u/d.png")
    md = "```mermaid\ngraph TD; A-->B\n```"
    cache = {}
    vp.convert_mermaid(md, {"access_token": "a"}, cache=cache)
    assert len(calls) == 1 and any(k.startswith("mermaid:") for k in cache)
    new_md, n = vp.convert_mermaid(md, {"access_token": "a"}, cache=cache)
    assert len(calls) == 1  # 캐시 히트 — kroki 재호출 없음
    assert "velcdn.com" in new_md


def test_http_network_error_raises_velog_error(home, monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(vp.urllib.request, "urlopen", boom)
    with pytest.raises(vp.VelogError):
        vp._http("https://v3.velog.io/graphql", method="POST", data=b"{}")


def test_cmd_update_flow(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD.replace("![스크린샷](assets/a.png)", "수정된 본문"), encoding="utf-8")
    md.with_suffix(".velog.json").write_text(json.dumps({
        "id": "p-1", "url_slug": "s", "username": "u", "title": "테스트 회고",
        "tags": ["테스트"], "thumbnail": None, "visibility": "private",
    }), encoding="utf-8")
    captured = {}

    def fake_edit(post_id, title, body, tags, thumbnail, url_slug, tokens,
                  temp=False, private=True, series_id=None):
        captured.update(post_id=post_id, private=private, body=body)
        return {"id": post_id, "url_slug": url_slug}

    monkeypatch.setattr(vp, "edit_post", fake_edit)
    assert vp.cmd_update(str(md)) == 0
    assert captured["post_id"] == "p-1" and captured["private"] is True  # 비공개 유지
    assert "수정된 본문" in captured["body"]
    assert md.with_suffix(".published.md").is_file()


def test_cmd_update_can_set_series(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD.replace("![스크린샷](assets/a.png)", ""), encoding="utf-8")
    md.with_suffix(".velog.json").write_text(json.dumps({
        "id": "p-1", "url_slug": "s", "username": "u", "title": "테스트 회고",
        "tags": ["테스트"], "thumbnail": None, "series_id": None, "visibility": "private",
    }), encoding="utf-8")
    captured = {}

    def fake_edit(post_id, title, body, tags, thumbnail, url_slug, tokens,
                  temp=False, private=True, series_id=None):
        captured["series_id"] = series_id
        return {"id": post_id, "url_slug": url_slug}

    monkeypatch.setattr(vp, "edit_post", fake_edit)
    assert vp.cmd_update(str(md), series_id="s-77") == 0
    assert captured["series_id"] == "s-77"
    sidecar = json.loads(md.with_suffix(".velog.json").read_text(encoding="utf-8"))
    assert sidecar["series_id"] == "s-77"  # 다음 update부터는 자동 유지


def test_cmd_update_missing_sidecar_exit_5(home, tmp_path):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD, encoding="utf-8")
    assert vp.cmd_update(str(md)) == 5


def test_cmd_publish_without_tokens_exit_2(home, tmp_path):
    md = tmp_path / "p.md"
    md.write_text(MD, encoding="utf-8")
    assert vp.cmd_publish(str(md)) == 2


def test_cmd_publish_without_title_exit_5(home, tmp_path):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text("제목 frontmatter 없음", encoding="utf-8")
    assert vp.cmd_publish(str(md)) == 5


def test_cmd_publish_auth_error_exit_2(home, tmp_path, monkeypatch):
    vp.save_tokens({"access_token": "a", "refresh_token": "r"})
    md = tmp_path / "p.md"
    md.write_text(MD.replace("![스크린샷](assets/a.png)", ""), encoding="utf-8")

    def raise_auth(*a, **k):
        raise vp.VelogError("인증 실패(401) — 토큰 만료 가능성. setup을 다시 실행하세요.")

    monkeypatch.setattr(vp, "write_post", raise_auth)
    assert vp.cmd_publish(str(md)) == 2
