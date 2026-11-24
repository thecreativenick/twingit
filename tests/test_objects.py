import shutil
import subprocess

import pytest

from twingit import Repo

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="real git not installed")


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def make_files(root):
    (root / "README.md").write_bytes(b"# demo\n")
    (root / "a.txt").write_bytes(b"alpha\n")
    (root / "a").mkdir()
    (root / "a" / "inner.txt").write_bytes(b"inner\n")
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "mod.py").write_bytes(b"print('hi')\n")
    (root / "empty").mkdir()


def test_roundtrip_blob(tmp_path):
    repo = Repo.init(tmp_path)
    oid = repo.write_object("blob", b"hello\n")
    assert oid == "ce013625030ba8dba906f756967f9e9ca394464a"  # git hash-object of "hello\n"
    assert repo.read_object(oid) == ("blob", b"hello\n")


def test_tree_parse_roundtrip(tmp_path):
    make_files(tmp_path)
    repo = Repo.init(tmp_path)
    tree = repo.write_tree()
    names = [e.name for e in repo.parse_tree(tree)]
    assert names == ["README.md", "a.txt", "a", "src"]  # git's tree sort order


@needs_git
def test_hash_object_matches_git(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(bytes(range(256)) * 3)
    repo = Repo.init(tmp_path / "r")
    assert repo.write_object("blob", f.read_bytes()) == git(tmp_path, "hash-object", str(f))


@needs_git
def test_write_tree_matches_git(tmp_path):
    make_files(tmp_path)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    expected = git(tmp_path, "write-tree")
    assert Repo(tmp_path).write_tree() == expected


@needs_git
def test_real_git_reads_our_commits(tmp_path):
    make_files(tmp_path)
    repo = Repo.init(tmp_path)
    c1 = repo.write_commit(repo.write_tree(), "first commit")
    (tmp_path / "a.txt").write_bytes(b"alpha v2\n")
    c2 = repo.write_commit(repo.write_tree(), "second commit", parents=[c1], timestamp=1_700_000_100)
    repo.update_ref("refs/heads/main", c2)

    git(tmp_path, "fsck", "--strict", "--no-dangling")
    assert git(tmp_path, "log", "--format=%H %s").splitlines() == [
        f"{c2} second commit",
        f"{c1} first commit",
    ]
    assert [(o, s) for o, s in repo.log()] == [(c2, "second commit"), (c1, "first commit")]
    # No index yet (that's a later milestone), so build one with git and check
    # the working tree matches our commit exactly.
    git(tmp_path, "read-tree", "HEAD")
    assert git(tmp_path, "status", "--porcelain") == ""
