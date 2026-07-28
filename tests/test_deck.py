import base64
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "skills" / "retro-ppt" / "assets" / "deck-template.html"
EMBED = ROOT / "skills" / "retro-ppt" / "scripts" / "embed_images.py"

spec = importlib.util.spec_from_file_location("embed_images", EMBED)
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_template_has_required_parts():
    text = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "<!-- SLIDES:START -->", "<!-- SLIDES:END -->",
        "@media print", "keydown", 'class="slide',
        "slide-title", "slide-section", "slide-quote", "slide-end",
    ):
        assert marker in text, f"템플릿에 {marker} 없음"


def test_template_no_external_requests():
    text = TEMPLATE.read_text(encoding="utf-8")
    # SVG 네임스페이스 xmlns 제외, 실제 리소스 로드 URL이 없어야 한다
    for token in ("http://", "https://"):
        for i, line in enumerate(text.splitlines(), 1):
            if token in line and "xmlns" not in line:
                raise AssertionError(f"외부 URL 발견 (줄 {i}): {line.strip()}")


def test_embed_rewrites_local_img_to_data_uri(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a.png").write_bytes(PNG)
    html = tmp_path / "deck.html"
    html.write_text('<img src="img/a.png"><img src="data:image/png;base64,xx">', encoding="utf-8")
    changed, missing = em.embed(html)
    out = html.read_text(encoding="utf-8")
    assert changed == 1 and missing == 0
    assert 'src="data:image/png;base64,' in out
    assert 'src="img/a.png"' not in out


def test_embed_missing_image_becomes_placeholder(tmp_path):
    html = tmp_path / "deck.html"
    html.write_text('<img src="nope.png" alt="스크린샷">', encoding="utf-8")
    changed, missing = em.embed(html)
    out = html.read_text(encoding="utf-8")
    assert missing == 1
    assert 'src="nope.png"' not in out
    assert "data:image/svg+xml;base64," in out


def test_embed_cli(tmp_path):
    (tmp_path / "a.png").write_bytes(PNG)
    html = tmp_path / "deck.html"
    html.write_text('<img src="a.png">', encoding="utf-8")
    rc = subprocess.run([sys.executable, str(EMBED), str(html)], capture_output=True).returncode
    assert rc == 0
    assert "data:image/png" in html.read_text(encoding="utf-8")
