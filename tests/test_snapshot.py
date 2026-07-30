import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro" / "scripts" / "snapshot.py"

spec = importlib.util.spec_from_file_location("snapshot", SCRIPT)
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def test_snapshot_saves_html_and_png(tmp_path, monkeypatch):
    html = tmp_path / "map.html"
    html.write_text("<h1>v1</h1>", encoding="utf-8")
    retro = tmp_path / "retro"
    shots = []

    def fake_shot(src, out, width=1280, height=800):
        Path(out).write_bytes(b"\x89PNGfake")
        shots.append(str(out))
        return Path(out)

    monkeypatch.setattr(sp, "shot", fake_shot)
    rc = sp.main([str(html), "카드 목록 버전", "--retro-dir", str(retro)])
    assert rc == 0
    saved = list((retro / "snapshots" / "map").glob("*"))
    names = sorted(p.suffix for p in saved)
    assert names == [".html", ".png"]
    assert "카드-목록-버전" in saved[0].stem  # 라벨의 공백은 -로
    assert len(shots) == 1


def test_snapshot_survives_browser_failure(tmp_path, monkeypatch):
    html = tmp_path / "deck.html"
    html.write_text("<h1>x</h1>", encoding="utf-8")
    retro = tmp_path / "retro"

    def boom(*a, **k):
        raise RuntimeError("브라우저 없음")

    monkeypatch.setattr(sp, "shot", boom)
    rc = sp.main([str(html), "라벨", "--retro-dir", str(retro)])
    assert rc == 0  # PNG 실패해도 HTML 보존은 성공
    saved = list((retro / "snapshots" / "deck").glob("*.html"))
    assert len(saved) == 1


def test_snapshot_skips_huge_html(tmp_path, monkeypatch):
    html = tmp_path / "big.html"
    html.write_text("x" * (6 * 1024 * 1024), encoding="utf-8")
    retro = tmp_path / "retro"
    monkeypatch.setattr(sp, "shot", lambda *a, **k: Path(a[1]).write_bytes(b"p") or Path(a[1]))
    rc = sp.main([str(html), "라벨", "--retro-dir", str(retro)])
    assert rc == 0
    saved = list((retro / "snapshots" / "big").glob("*"))
    assert [p.suffix for p in saved] == [".png"]  # 용량 초과 HTML은 스킵, PNG만
