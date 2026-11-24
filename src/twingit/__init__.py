"""twingit: a Git implementation whose repositories real git can't tell apart."""

from .objects import MODE_FILE, MODE_TREE, Repo, TreeEntry

__all__ = ["Repo", "TreeEntry", "MODE_FILE", "MODE_TREE"]
