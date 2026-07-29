import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "retro" / "scripts" / "inventory.py"

spec = importlib.util.spec_from_file_location("inventory", SCRIPT)
inv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inv)


def make_session(path, title, ts_list):
    lines = [json.dumps({"type": "ai-title", "title": title})]
    for i, ts in enumerate(ts_list):
        lines.append(json.dumps({
            "type": "user", "isSidechain": False, "timestamp": ts,
            "message": {"role": "user", "content": f"메시지 {i}"},
        }))
    path.write_text("\n".join(lines), encoding="utf-8")


def make_repo(tmp_path, commits):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    for msg, date in commits:
        (repo / "f.txt").write_text(msg)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", msg],
            cwd=repo, check=True,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "PATH": "/usr/bin:/bin"},
        )
    return repo


def test_commit_assignment(tmp_path):
    s1 = tmp_path / "s1.jsonl"
    make_session(s1, "인증 구현", ["2026-07-10T10:00:00Z", "2026-07-10T11:00:00Z"])
    repo = make_repo(tmp_path, [
        ("feat: 로그인", "2026-07-10T10:30:00+00:00"),      # 세션 창 안
        ("chore: 옛날 작업", "2026-06-01T09:00:00+00:00"),  # 창 밖 → 미귀속
    ])
    rows = [inv.session_row(s1)]
    commits = inv.git_commits(str(repo))
    unassigned = inv.assign(commits, rows)
    assert len(rows[0]["commits"]) == 1 and "로그인" in rows[0]["commits"][0]["subject"]
    assert len(unassigned) == 1 and "옛날" in unassigned[0]["subject"]


def test_render_contains_table_and_orphan_commits(tmp_path):
    s1 = tmp_path / "s1.jsonl"
    make_session(s1, "배포 삽질", ["2026-07-12T09:00:00Z", "2026-07-12T09:40:00Z"])
    rows = [inv.session_row(s1)]
    text = inv.render(rows, [{"hash": "abc1234", "ts": rows[0]["first"], "subject": "고아 커밋"}], True)
    assert "배포 삽질" in text and "40분" in text
    assert "세션 기록이 없는 커밋" in text and "고아 커밋" in text


def test_no_git_graceful(tmp_path):
    assert inv.git_commits(str(tmp_path)) is None  # git 저장소 아님


def test_cli_out(tmp_path):
    s1 = tmp_path / "s1.jsonl"
    make_session(s1, "테스트", ["2026-07-01T10:00:00Z"])
    out = tmp_path / "inv.md"
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--sessions", str(s1), "--repo", str(tmp_path), "--out", str(out)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 0 and "프로젝트 인벤토리" in out.read_text(encoding="utf-8")


def test_cli_no_sessions_exit_1(tmp_path):
    rc = subprocess.run(
        [sys.executable, str(SCRIPT), "--sessions", str(tmp_path / "nope.jsonl"), "--repo", str(tmp_path)],
        capture_output=True, text=True,
    ).returncode
    assert rc == 1
