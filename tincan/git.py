"""Concrete git shell. Pull ff-only, commit owned paths, push, blame, public probe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .types import Seq


@dataclass(frozen=True)
class GitAuthor:
    name: str
    email: str


def require_repo(root: Path) -> None:
    raise NotImplementedError


def require_branch(root: Path, branch: str) -> None:
    """Die unless HEAD equals the room branch."""
    raise NotImplementedError


def pull(root: Path) -> None:
    """git pull --ff-only. ConflictError on non-fast-forward."""
    raise NotImplementedError


def commit_owned(root: Path, paths: list[Path], message: str, author: GitAuthor) -> None:
    """git add and git commit --only those paths as author.

    author comes from room.json, not from git config. No-op if the index is
    unchanged. Same dirty bytes become the same commit.
    """
    raise NotImplementedError


def push(root: Path) -> None:
    raise NotImplementedError


def author_of_line(root: Path, path: Path, seq: Seq) -> GitAuthor:
    """Blame the line that carries seq."""
    raise NotImplementedError


def remote_url(root: Path) -> str:
    raise NotImplementedError


def remote_is_public(root: Path) -> bool:
    raise NotImplementedError
