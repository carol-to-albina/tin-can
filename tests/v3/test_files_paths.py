from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tincan import files
from tincan.types import (
    DEFAULT_LATENCY_SEC,
    Autonomy,
    EventRef,
    MemberId,
    Mode,
    ProtocolError,
    Seq,
    WakeType,
)

ROOM = {
    "protocol": 3,
    "room": "tincan",
    "repo": "carol-to-albina/tincan",
    "branch": "master",
    "host": "carol",
    "members": {
        "albina": {"github": "enjojoy", "display": "Albina"},
        "carol": {"github": "rainbowpuffpuff", "display": "Carol"},
    },
}


class PathTests(unittest.TestCase):
    def test_cabinet_paths(self) -> None:
        root = Path("/tmp/repo")
        self.assertEqual(files.cabinet_dir(root), Path("/tmp/repo/.tincan"))
        self.assertEqual(files.room_path(root), Path("/tmp/repo/.tincan/room.json"))
        self.assertEqual(
            files.who_path(root, MemberId("carol")),
            Path("/tmp/repo/.tincan/who/carol.json"),
        )
        self.assertEqual(
            files.out_path(root, MemberId("carol")),
            Path("/tmp/repo/.tincan/out/carol.ndjson"),
        )
        self.assertEqual(
            files.pos_path(root, MemberId("albina")),
            Path("/tmp/repo/.tincan/pos/albina"),
        )
        self.assertEqual(files.local_me_path(root), Path("/tmp/repo/.tincan/local/me"))


class RoomTests(unittest.TestCase):
    def test_parse_room(self) -> None:
        cfg = files.parse_room(json.dumps(ROOM))
        self.assertEqual(cfg.protocol, 3)
        self.assertEqual(cfg.room, "tincan")
        self.assertEqual(cfg.repo, "carol-to-albina/tincan")
        self.assertEqual(cfg.branch, "master")
        self.assertEqual(cfg.host, "carol")
        self.assertEqual(
            cfg.roster,
            {
                "albina": ("enjojoy", "Albina"),
                "carol": ("rainbowpuffpuff", "Carol"),
            },
        )

    def test_parse_room_defaults_branch_to_master(self) -> None:
        raw = dict(ROOM)
        del raw["branch"]
        self.assertEqual(files.parse_room(json.dumps(raw)).branch, "master")

    def test_parse_room_rejects_protocol_2(self) -> None:
        raw = dict(ROOM, protocol=2)
        with self.assertRaises(ProtocolError):
            files.parse_room(json.dumps(raw))

    def test_parse_room_rejects_missing_protocol(self) -> None:
        raw = dict(ROOM)
        del raw["protocol"]
        with self.assertRaises(ProtocolError):
            files.parse_room(json.dumps(raw))

    def test_parse_room_rejects_member_without_github(self) -> None:
        raw = dict(ROOM, members={"carol": {"display": "Carol"}})
        with self.assertRaises(ProtocolError):
            files.parse_room(json.dumps(raw))

    def test_parse_room_rejects_host_outside_roster(self) -> None:
        raw = dict(ROOM, host="dana")
        with self.assertRaises(ProtocolError):
            files.parse_room(json.dumps(raw))


class WhoTests(unittest.TestCase):
    def test_parse_who_full(self) -> None:
        raw = json.dumps(
            {
                "display": "Albina",
                "mode": "webhook",
                "autonomy": "auto",
                "latency_sec": 60,
                "wake": {"type": "http", "url": "https://hook.example/a", "key": "s3cr3t"},
            }
        )
        who = files.parse_who(raw)
        self.assertEqual(who.display, "Albina")
        self.assertIs(who.mode, Mode.WEBHOOK)
        self.assertIs(who.autonomy, Autonomy.AUTO)
        self.assertEqual(who.latency_sec, 60)
        self.assertIs(who.wake.type, WakeType.HTTP)
        self.assertEqual(who.wake.url, "https://hook.example/a")
        self.assertEqual(who.wake.key, "s3cr3t")

    def test_parse_who_empty_object_is_defaults(self) -> None:
        who = files.parse_who("{}")
        self.assertEqual(who.display, "")
        self.assertIs(who.mode, Mode.HUMAN)
        self.assertIs(who.autonomy, Autonomy.ASK)
        self.assertEqual(who.latency_sec, DEFAULT_LATENCY_SEC)
        self.assertIs(who.wake.type, WakeType.NONE)
        self.assertEqual(who.wake.url, "")
        self.assertEqual(who.wake.key, "")

    def test_parse_who_rejects_unknown_autonomy(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_who(json.dumps({"autonomy": "yolo"}))

    def test_parse_who_rejects_mailto_wake(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_who(json.dumps({"wake": {"type": "mailto"}}))

    def test_parse_who_rejects_non_positive_latency(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_who(json.dumps({"latency_sec": 0}))


class MergeMemberTests(unittest.TestCase):
    def test_missing_who_uses_defaults(self) -> None:
        member = files.merge_member(MemberId("carol"), "rainbowpuffpuff", "Carol", None)
        self.assertEqual(member.id, "carol")
        self.assertEqual(member.github, "rainbowpuffpuff")
        self.assertEqual(member.display, "Carol")
        self.assertIs(member.mode, Mode.HUMAN)
        self.assertIs(member.autonomy, Autonomy.ASK)
        self.assertEqual(member.latency_sec, DEFAULT_LATENCY_SEC)
        self.assertIs(member.wake.type, WakeType.NONE)

    def test_who_display_overrides_room_display(self) -> None:
        who = files.parse_who(json.dumps({"display": "Al", "autonomy": "auto"}))
        member = files.merge_member(MemberId("albina"), "enjojoy", "Albina", who)
        self.assertEqual(member.display, "Al")
        self.assertIs(member.autonomy, Autonomy.AUTO)

    def test_who_cannot_override_github(self) -> None:
        who = files.parse_who(json.dumps({"github": "forged"}))
        member = files.merge_member(MemberId("albina"), "enjojoy", "Albina", who)
        self.assertEqual(member.github, "enjojoy")


class LoadMembersTests(unittest.TestCase):
    def test_who_defaults_on_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files.room_path(root).parent.mkdir(parents=True)
            files.room_path(root).write_text(json.dumps(ROOM), encoding="utf-8")
            files.who_path(root, MemberId("albina")).parent.mkdir(parents=True)
            files.who_path(root, MemberId("albina")).write_text(
                json.dumps({"autonomy": "auto", "mode": "daemon"}), encoding="utf-8"
            )

            members = files.load_members(root)

            self.assertEqual(sorted(members), ["albina", "carol"])
            self.assertIs(members[MemberId("albina")].autonomy, Autonomy.AUTO)
            self.assertIs(members[MemberId("albina")].mode, Mode.DAEMON)
            self.assertEqual(members[MemberId("albina")].display, "Albina")
            self.assertIs(members[MemberId("carol")].autonomy, Autonomy.ASK)
            self.assertIs(members[MemberId("carol")].mode, Mode.HUMAN)
            self.assertEqual(members[MemberId("carol")].latency_sec, 86400)

    def test_missing_room_file_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProtocolError):
                files.load_members(Path(tmp))


class RefTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        ref = files.parse_ref("carol:4")
        self.assertEqual(ref, EventRef(MemberId("carol"), Seq(4)))
        self.assertEqual(str(ref), "carol:4")
        self.assertEqual(files.parse_ref(str(ref)), ref)

    def test_event_ref_parse_is_the_same_function(self) -> None:
        self.assertEqual(EventRef.parse("albina:12"), EventRef(MemberId("albina"), Seq(12)))

    def test_bad_refs(self) -> None:
        for raw in ("", "carol", "carol:", ":4", "carol:0", "carol:-1", "carol:x", "a:b:1", "carol:1.5"):
            with self.subTest(raw=raw):
                with self.assertRaises(ProtocolError):
                    files.parse_ref(raw)


if __name__ == "__main__":
    unittest.main()
