import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro" / "scripts" / "html_shot.py"

spec = importlib.util.spec_from_file_location("html_shot", SCRIPT)
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)


def test_find_browser_env_first(tmp_path, monkeypatch):
    fake = tmp_path / "mychrome.exe"
    fake.write_bytes(b"x")
    monkeypatch.setenv("CHROME_PATH", str(fake))
    assert hs.find_browser() == str(fake)


def test_find_browser_none(monkeypatch):
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(hs, "WINDOWS_BROWSERS", [])
    monkeypatch.setattr(hs, "LINUX_BROWSERS", [])
    assert hs.find_browser() is None


def test_shot_without_browser_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(hs, "WINDOWS_BROWSERS", [])
    monkeypatch.setattr(hs, "LINUX_BROWSERS", [])
    html = tmp_path / "a.html"
    html.write_text("<h1>x</h1>", encoding="utf-8")
    with pytest.raises(RuntimeError):
        hs.shot(html, tmp_path / "out.png")


@pytest.mark.skipif(hs.find_browser() is None, reason="브라우저 없음")
def test_shot_real_render(tmp_path):
    html = tmp_path / "card.html"
    html.write_text(
        "<body style='background:#111;color:#eee;font-size:40px'>세션 228회 도구 호출</body>",
        encoding="utf-8",
    )
    out = hs.shot(html, tmp_path / "out.png", width=800, height=400)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 1000


@pytest.mark.skipif(hs.find_browser() is None, reason="브라우저 없음")
def test_cli(tmp_path):
    import subprocess, sys
    html = tmp_path / "a.html"
    html.write_text("<h1>CLI</h1>", encoding="utf-8")
    out = tmp_path / "o.png"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), str(html), str(out), "--width", "600", "--height", "300"],
        capture_output=True, text=True,
    ).returncode
    assert rc == 0 and out.stat().st_size > 0
