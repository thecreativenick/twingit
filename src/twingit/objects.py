"""Loose-object storage in git's on-disk format: blobs, trees and commits.

Every object is stored as zlib("<type> <size>\\0<body>") under
.git/objects/<first 2 hex>/<remaining 38 hex>, named by the SHA-1 of the
uncompressed bytes. Matching git byte for byte here is what lets real git
read repositories this tool writes.
"""

from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass
from pathlib import Path

MODE_FILE = "100644"
MODE_TREE = "40000"


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    name: str
    oid: str

    def sort_key(self) -> bytes:
        # git sorts tree entries by name, comparing directories as if they
        # ended in "/" (so "a.txt" sorts before directory "a").
        name = self.name.encode()
        return name + b"/" if self.mode == MODE_TREE else name


class Repo:
    def __init__(self, path: str | Path):
        self.root = Path(path)
        self.gitdir = self.root / ".git"

    # ------------------------------------------------------------------ init
    @classmethod
    def init(cls, path: str | Path, branch: str = "main") -> "Repo":
        repo = cls(path)
        g = repo.gitdir
        for sub in ("objects", "refs/heads", "refs/tags"):
            (g / sub).mkdir(parents=True, exist_ok=True)
        _write_text(g / "HEAD", f"ref: refs/heads/{branch}\n")
        _write_text(
            g / "config",
            "[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = false\n",
        )
        return repo

    # --------------------------------------------------------------- objects
    def object_path(self, oid: str) -> Path:
        return self.gitdir / "objects" / oid[:2] / oid[2:]

    def write_object(self, kind: str, body: bytes) -> str:
        raw = f"{kind} {len(body)}".encode() + b"\0" + body
        oid = hashlib.sha1(raw).hexdigest()
        path = self.object_path(oid)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zlib.compress(raw))
        return oid

    def read_object(self, oid: str) -> tuple[str, bytes]:
        raw = zlib.decompress(self.object_path(oid).read_bytes())
        header, _, body = raw.partition(b"\0")
        kind, size = header.split(b" ")
        if int(size) != len(body):
            raise ValueError(f"object {oid}: size header {size!r} != {len(body)}")
        return kind.decode(), body

    # ----------------------------------------------------------------- trees
    def write_tree_entries(self, entries: list[TreeEntry]) -> str:
        body = b"".join(
            f"{e.mode} {e.name}".encode() + b"\0" + bytes.fromhex(e.oid)
            for e in sorted(entries, key=TreeEntry.sort_key)
        )
        return self.write_object("tree", body)

    def parse_tree(self, oid: str) -> list[TreeEntry]:
        kind, body = self.read_object(oid)
        if kind != "tree":
            raise ValueError(f"{oid} is a {kind}, not a tree")
        entries, i = [], 0
        while i < len(body):
            sp = body.index(b" ", i)
            nul = body.index(b"\0", sp)
            mode = body[i:sp].decode()
            name = body[sp + 1 : nul].decode()
            entries.append(TreeEntry(mode, name, body[nul + 1 : nul + 21].hex()))
            i = nul + 21
        return entries

    def write_tree(self, directory: str | Path | None = None) -> str:
        """Snapshot a working directory (skipping .git) as a tree object.

        Empty directories are skipped, as git does.
        """
        directory = Path(directory) if directory is not None else self.root
        entries = []
        for child in directory.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                if not any(p.is_file() for p in child.rglob("*")):
                    continue
                entries.append(TreeEntry(MODE_TREE, child.name, self.write_tree(child)))
            else:
                oid = self.write_object("blob", child.read_bytes())
                entries.append(TreeEntry(MODE_FILE, child.name, oid))
        return self.write_tree_entries(entries)

    # --------------------------------------------------------------- commits
    def write_commit(
        self,
        tree: str,
        message: str,
        parents: list[str] | None = None,
        author: str = "Example Author <author@example.com>",
        timestamp: int = 1_700_000_000,
        tz: str = "+0000",
    ) -> str:
        lines = [f"tree {tree}"]
        lines += [f"parent {p}" for p in parents or []]
        lines.append(f"author {author} {timestamp} {tz}")
        lines.append(f"committer {author} {timestamp} {tz}")
        body = "\n".join(lines) + "\n\n" + message
        if not body.endswith("\n"):
            body += "\n"
        return self.write_object("commit", body.encode())

    # ------------------------------------------------------------------ refs
    def update_ref(self, ref: str, oid: str) -> None:
        path = self.gitdir / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(path, oid + "\n")

    def resolve(self, ref: str = "HEAD") -> str | None:
        path = self.gitdir / ref
        if not path.exists():
            return None
        text = path.read_text().strip()
        if text.startswith("ref: "):
            return self.resolve(text[5:])
        return text

    def log(self, ref: str = "HEAD") -> list[tuple[str, str]]:
        """First-parent history as (oid, subject line) pairs, newest first."""
        out, oid = [], self.resolve(ref)
        while oid:
            _, body = self.read_object(oid)
            headers, _, message = body.decode().partition("\n\n")
            out.append((oid, message.splitlines()[0] if message else ""))
            parents = [l[7:] for l in headers.splitlines() if l.startswith("parent ")]
            oid = parents[0] if parents else None
        return out


def _write_text(path: Path, text: str) -> None:
    # Always LF, even on Windows: git expects exact bytes.
    path.write_text(text, encoding="utf-8", newline="\n")
