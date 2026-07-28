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


def test_upload_http_error_raises(home, tmp_path, monkeypatch):
    img = tmp_path / "x.png"
    img.write_bytes(b"img")
    monkeypatch.setattr(vp, "_http", lambda *a, **k: (500, [], b"boom"))
    with pytest.raises(vp.VelogError):
        vp.upload_image(img, {"access_token": "a"})
