"""Argv in, JSON or chat out. No cabinet rules beyond flag mapping."""

from __future__ import annotations

import argparse
import sys

from .room import Room
from .types import MemberId


def build_parser() -> argparse.ArgumentParser:
    raise NotImplementedError


def resolve_me(args: argparse.Namespace, room: Room) -> MemberId:
    """args.me, then TINCAN_ME, then .tincan/local/me."""
    raise NotImplementedError


def print_inbox(inbox, members, fmt: str) -> None:
    raise NotImplementedError


def cmd_init(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_join(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_doctor(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_sync(args: argparse.Namespace) -> None:
    """Room.sync, optional ack and publish, print JSON or chat."""
    raise NotImplementedError


def cmd_inbox(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_ack(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_post(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_claim(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_done(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_fail(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_approve(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_deny(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_revoke(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_tasks(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_grants(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_publish(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_notify(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_hook_set(args: argparse.Namespace) -> None:
    raise NotImplementedError


def cmd_migrate(args: argparse.Namespace) -> None:
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
