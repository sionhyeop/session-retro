import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro-blog" / "scripts" / "style_learn.py"

spec = importlib.util.spec_from_file_location("style_learn", SCRIPT)
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)


def graphql_response(data):
    return 200, [], json.dumps({"data": data}).encode()


def test_fetch_posts_payload_and_private_filter(monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["url"], captured["payload"] = url, json.loads(data)
        return graphql_response({"posts": [
            {"title": "공개 글", "url_slug": "a", "is_private": False, "released_at": "2026-01-01"},
            {"title": "비밀 글", "url_slug": "b", "is_private": True, "released_at": "2026-01-02"},
        ]})

    monkeypatch.setattr(sl, "_http", fake_http)
    posts = sl.fetch_posts("testuser", limit=10)
    assert captured["url"] == sl.V2_GRAPHQL
    assert captured["payload"]["variables"] == {"username": "testuser", "limit": 10}
    assert [p["url_slug"] for p in posts] == ["a"]  # 비공개 글 제외


def test_fetch_body_payload(monkeypatch):
    captured = {}

    def fake_http(url, method="GET", headers=None, data=None):
        captured["payload"] = json.loads(data)
        return graphql_response({"post": {"title": "공개 글", "body": "본문입니다."}})

    monkeypatch.setattr(sl, "_http", fake_http)
    post = sl.fetch_body("testuser", "a")
    assert post["body"] == "본문입니다."
    assert captured["payload"]["variables"] == {"username": "testuser", "url_slug": "a"}


def test_ending_stats_counts():
    stats = sl.ending_stats("이렇게 했습니다. 좋더라고요. 왜 안 될까요? 결국 고쳤다. 재밌었어요!")
    assert stats["습니다"] == 1
    assert stats["어요/아요"] == 1
    assert stats["라고요/네요/거든요"] == 1
    assert stats["다."] == 1
    assert stats["물음표"] == 1 and stats["느낌표"] == 1


def test_build_corpus_truncates_and_includes_stats():
    posts = [{"title": "긴 글", "body": "습니다. " * 2000, "released_at": "2026-01-01"}]
    corpus = sl.build_corpus("testuser", posts, max_chars=500)
    assert "긴 글" in corpus and "문체 통계" in corpus
    assert "…(이하 생략)" in corpus
    assert len(corpus) < 3000


def test_main_no_public_posts_exit_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sl, "fetch_posts", lambda u, limit=10: [])
    rc = sl.main(["testuser", "--out", str(tmp_path / "c.md")])
    assert rc == 1
    assert "공개 글이 없습니다" in capsys.readouterr().err


def test_main_writes_corpus(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "fetch_posts", lambda u, limit=10: [
        {"title": "글1", "url_slug": "a", "is_private": False, "released_at": "2026-01-01"},
    ])
    monkeypatch.setattr(sl, "fetch_body", lambda u, s: {"title": "글1", "body": "본문이었습니다."})
    out = tmp_path / "corpus.md"
    rc = sl.main(["testuser", "--out", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "글1" in text and "본문이었습니다." in text
