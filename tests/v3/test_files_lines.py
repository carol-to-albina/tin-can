from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from tincan import files
from tincan.types import (
    Claim,
    Cot,
    Deny,
    Done,
    EventRef,
    Fail,
    GrantApproved,
    GrantRequest,
    Kind,
    MemberId,
    ProtocolError,
    Receipt,
    Revoke,
    Speech,
    TaskPosted,
)

CAROL = MemberId("carol")
ALBINA = MemberId("albina")
TS = "2026-09-20T12:00:00Z"


def speech(seq: int, body: str = "hello", to: str = "all", ts: str = TS):
    return files.build_event(
        writer=CAROL, seq=seq, to=to, kind=Kind.SPEECH, body=body, ts=ts
    )


class BuildEventTests(unittest.TestCase):
    def test_speech(self) -> None:
        event = speech(1)
        self.assertIsInstance(event, Speech)
        self.assertEqual(event.kind, Kind.SPEECH)
        self.assertEqual(event.meta.writer, "carol")
        self.assertEqual(event.meta.seq, 1)
        self.assertEqual(event.meta.ts, TS)
        self.assertEqual(event.meta.to, "all")
        self.assertEqual(event.body, "hello")
        self.assertEqual(event.meta.ref(), EventRef(CAROL, 1))

    def test_ref_kinds_take_to_from_the_referenced_writer(self) -> None:
        event = files.build_event(
            writer=ALBINA,
            seq=3,
            to="",
            kind=Kind.CLAIM,
            body="",
            ref=EventRef(CAROL, 1),
        )
        self.assertIsInstance(event, Claim)
        self.assertEqual(event.meta.to, "carol")
        self.assertEqual(event.ref, EventRef(CAROL, 1))

    def test_ref_kind_refuses_a_to_that_is_not_the_referenced_writer(self) -> None:
        with self.assertRaises(ProtocolError):
            files.build_event(
                writer=ALBINA,
                seq=3,
                to="albina",
                kind=Kind.CLAIM,
                body="",
                ref=EventRef(CAROL, 1),
            )

    def test_ref_kinds_refuse_a_missing_ref(self) -> None:
        for kind in (Kind.CLAIM, Kind.DONE, Kind.FAIL, Kind.GRANT, Kind.DENY, Kind.REVOKE, Kind.COT, Kind.RECEIPT):
            with self.subTest(kind=kind):
                with self.assertRaises(ProtocolError):
                    files.build_event(
                        writer=ALBINA, seq=1, to="carol", kind=kind, body="x"
                    )

    def test_plain_kinds_refuse_a_ref(self) -> None:
        for kind in (Kind.SPEECH, Kind.TASK, Kind.GRANT_REQUEST):
            with self.subTest(kind=kind):
                with self.assertRaises(ProtocolError):
                    files.build_event(
                        writer=CAROL,
                        seq=1,
                        to="albina",
                        kind=kind,
                        body="x",
                        ref=EventRef(CAROL, 1),
                    )

    def test_body_required_kinds_refuse_an_empty_body(self) -> None:
        with self.assertRaises(ProtocolError):
            files.build_event(writer=CAROL, seq=1, to="albina", kind=Kind.TASK, body="  ")
        with self.assertRaises(ProtocolError):
            files.build_event(
                writer=CAROL,
                seq=1,
                to="albina",
                kind=Kind.COT,
                body="",
                ref=EventRef(ALBINA, 1),
            )

    def test_bodyless_kinds_refuse_a_body(self) -> None:
        with self.assertRaises(ProtocolError):
            files.build_event(
                writer=ALBINA,
                seq=1,
                to="carol",
                kind=Kind.CLAIM,
                body="mine",
                ref=EventRef(CAROL, 1),
            )

    def test_deny_carries_an_optional_reason(self) -> None:
        event = files.build_event(
            writer=ALBINA,
            seq=1,
            to="carol",
            kind=Kind.DENY,
            body="not today",
            ref=EventRef(CAROL, 1),
        )
        self.assertIsInstance(event, Deny)
        self.assertEqual(event.body, "not today")
        bare = files.build_event(
            writer=ALBINA, seq=2, to="carol", kind=Kind.DENY, body="", ref=EventRef(CAROL, 1)
        )
        self.assertEqual(bare.body, "")

    def test_capabilities_and_expires_only_on_grant_request(self) -> None:
        request = files.build_event(
            writer=CAROL,
            seq=1,
            to="albina",
            kind=Kind.GRANT_REQUEST,
            body="need cot",
            capabilities=("share_hidden_cot",),
            expires="2026-09-20T16:00:00Z",
        )
        self.assertIsInstance(request, GrantRequest)
        self.assertEqual(request.capabilities, ("share_hidden_cot",))
        self.assertEqual(request.expires, "2026-09-20T16:00:00Z")
        with self.assertRaises(ProtocolError):
            files.build_event(
                writer=CAROL,
                seq=1,
                to="albina",
                kind=Kind.SPEECH,
                body="hi",
                capabilities=("share_hidden_cot",),
            )
        with self.assertRaises(ProtocolError):
            files.build_event(
                writer=CAROL,
                seq=1,
                to="albina",
                kind=Kind.TASK,
                body="hi",
                expires="2026-09-20T16:00:00Z",
            )

    def test_bad_seq_and_ts(self) -> None:
        with self.assertRaises(ProtocolError):
            files.build_event(writer=CAROL, seq=0, to="all", kind=Kind.SPEECH, body="hi")
        with self.assertRaises(ProtocolError):
            files.build_event(
                writer=CAROL, seq=1, to="all", kind=Kind.SPEECH, body="hi", ts="2026-09-20 12:00"
            )

    def test_missing_to(self) -> None:
        with self.assertRaises(ProtocolError):
            files.build_event(writer=CAROL, seq=1, to="", kind=Kind.SPEECH, body="hi")

    def test_default_ts_is_utc_now(self) -> None:
        event = speech(1, ts=None)
        self.assertRegex(event.meta.ts, r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class FormatLineTests(unittest.TestCase):
    def test_speech_matches_the_spec_example(self) -> None:
        self.assertEqual(
            files.format_line(speech(1)),
            '{"seq":1,"ts":"2026-09-20T12:00:00Z","to":"all","kind":"speech","body":"hello"}',
        )

    def test_claim_carries_ref_and_no_body(self) -> None:
        event = files.build_event(
            writer=ALBINA, seq=2, to="", kind=Kind.CLAIM, body="", ref=EventRef(CAROL, 1), ts=TS
        )
        self.assertEqual(
            files.format_line(event),
            '{"seq":2,"ts":"2026-09-20T12:00:00Z","to":"carol","kind":"claim","ref":"carol:1"}',
        )

    def test_grant_request_carries_capabilities_and_expires(self) -> None:
        event = files.build_event(
            writer=CAROL,
            seq=1,
            to="albina",
            kind=Kind.GRANT_REQUEST,
            body="need cot",
            capabilities=("share_hidden_cot",),
            expires="2026-09-20T16:00:00Z",
            ts=TS,
        )
        self.assertEqual(
            files.format_line(event),
            '{"seq":1,"ts":"2026-09-20T12:00:00Z","to":"albina","kind":"grant_request",'
            '"body":"need cot","capabilities":["share_hidden_cot"],'
            '"expires":"2026-09-20T16:00:00Z"}',
        )

    def test_no_id_no_actor_no_grant_status(self) -> None:
        line = files.format_line(speech(1))
        for gone in ('"id"', '"actor"', '"grant_status"'):
            self.assertNotIn(gone, line)

    def test_unicode_stays_literal(self) -> None:
        line = files.format_line(speech(1, body="don't wait \u2014 ship"))
        self.assertIn("\u2014", line)


class ParseLineTests(unittest.TestCase):
    def test_round_trip_every_kind(self) -> None:
        events = [
            speech(1),
            files.build_event(writer=CAROL, seq=1, to="albina", kind=Kind.TASK, body="job", ts=TS),
            files.build_event(
                writer=ALBINA, seq=1, to="", kind=Kind.CLAIM, body="", ref=EventRef(CAROL, 1), ts=TS
            ),
            files.build_event(
                writer=ALBINA, seq=1, to="", kind=Kind.DONE, body="pr", ref=EventRef(CAROL, 1), ts=TS
            ),
            files.build_event(
                writer=ALBINA, seq=1, to="", kind=Kind.FAIL, body="why", ref=EventRef(CAROL, 1), ts=TS
            ),
            files.build_event(
                writer=CAROL,
                seq=1,
                to="albina",
                kind=Kind.GRANT_REQUEST,
                body="need",
                capabilities=("share_hidden_cot",),
                expires="2026-09-20T16:00:00Z",
                ts=TS,
            ),
            files.build_event(
                writer=ALBINA, seq=1, to="", kind=Kind.GRANT, body="", ref=EventRef(CAROL, 1), ts=TS
            ),
            files.build_event(
                writer=ALBINA, seq=1, to="", kind=Kind.DENY, body="no", ref=EventRef(CAROL, 1), ts=TS
            ),
            files.build_event(
                writer=ALBINA, seq=1, to="", kind=Kind.REVOKE, body="", ref=EventRef(CAROL, 1), ts=TS
            ),
            files.build_event(
                writer=CAROL, seq=1, to="", kind=Kind.COT, body="think", ref=EventRef(ALBINA, 1), ts=TS
            ),
            files.build_event(
                writer=CAROL, seq=1, to="", kind=Kind.RECEIPT, body="ok", ref=EventRef(ALBINA, 1), ts=TS
            ),
        ]
        classes = [
            Speech,
            TaskPosted,
            Claim,
            Done,
            Fail,
            GrantRequest,
            GrantApproved,
            Deny,
            Revoke,
            Cot,
            Receipt,
        ]
        self.assertEqual(len(events), len(Kind))
        for event, cls in zip(events, classes):
            with self.subTest(kind=event.kind):
                back = files.parse_line(event.meta.writer, event.meta.seq, files.format_line(event))
                self.assertIsInstance(back, cls)
                self.assertEqual(back, event)

    def test_seq_must_equal_the_line_position(self) -> None:
        line = files.format_line(speech(1))
        with self.assertRaises(ProtocolError):
            files.parse_line(CAROL, 2, line)

    def test_unknown_kind(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_line(
                CAROL, 1, '{"seq":1,"ts":"' + TS + '","to":"all","kind":"vibe","body":"hi"}'
            )

    def test_ref_kind_without_ref(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_line(
                ALBINA, 1, '{"seq":1,"ts":"' + TS + '","to":"carol","kind":"claim"}'
            )

    def test_body_required_kind_without_body(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_line(CAROL, 1, '{"seq":1,"ts":"' + TS + '","to":"all","kind":"speech"}')

    def test_missing_ts_and_to(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_line(CAROL, 1, '{"seq":1,"to":"all","kind":"speech","body":"hi"}')
        with self.assertRaises(ProtocolError):
            files.parse_line(CAROL, 1, '{"seq":1,"ts":"' + TS + '","kind":"speech","body":"hi"}')

    def test_ts_needs_a_z(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_line(
                CAROL, 1, '{"seq":1,"ts":"2026-09-20T12:00:00+02:00","to":"all","kind":"speech","body":"hi"}'
            )

    def test_bad_json(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_line(CAROL, 1, "{not json")


class OutboxTests(unittest.TestCase):
    def write(self, root: Path, writer: MemberId, text: str) -> Path:
        path = files.out_path(root, writer)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_and_empty_files_are_empty_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(files.load_outbox(root, CAROL), [])
            self.write(root, CAROL, "")
            self.assertEqual(files.load_outbox(root, CAROL), [])

    def test_blank_lines_do_not_consume_seq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "\n".join(
                [
                    "",
                    files.format_line(speech(1)),
                    "   ",
                    files.format_line(speech(2, body="two")),
                    "",
                ]
            )
            self.write(root, CAROL, body + "\n")
            events = files.load_outbox(root, CAROL)
            self.assertEqual([int(e.meta.seq) for e in events], [1, 2])
            self.assertEqual([e.body for e in events], ["hello", "two"])

    def test_gap_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                CAROL,
                files.format_line(speech(1)) + "\n" + files.format_line(speech(3)) + "\n",
            )
            with self.assertRaises(ProtocolError):
                files.load_outbox(root, CAROL)

    def test_duplicate_seq_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(
                root,
                CAROL,
                files.format_line(speech(1)) + "\n" + files.format_line(speech(1, body="again")) + "\n",
            )
            with self.assertRaises(ProtocolError):
                files.load_outbox(root, CAROL)

    def test_first_seq_must_be_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, CAROL, files.format_line(speech(2)) + "\n")
            with self.assertRaises(ProtocolError):
                files.load_outbox(root, CAROL)

    def test_next_seq(self) -> None:
        self.assertEqual(files.next_seq([]), 1)
        self.assertEqual(files.next_seq([speech(1), speech(2)]), 3)

    def test_append_then_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = files.append_outbox(root, speech(1))
            self.assertEqual(path, files.out_path(root, CAROL))
            files.append_outbox(root, speech(2, body="two"))
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                files.format_line(speech(1)) + "\n" + files.format_line(speech(2, body="two")) + "\n",
            )
            self.assertEqual(len(files.load_outbox(root, CAROL)), 2)

    def test_identical_last_line_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files.append_outbox(root, speech(1))
            before = files.out_path(root, CAROL).read_text(encoding="utf-8")
            files.append_outbox(root, speech(1))
            files.append_outbox(root, speech(1))
            self.assertEqual(files.out_path(root, CAROL).read_text(encoding="utf-8"), before)
            self.assertEqual(len(files.load_outbox(root, CAROL)), 1)

    def test_same_seq_with_different_bytes_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files.append_outbox(root, speech(1))
            with self.assertRaises(ProtocolError):
                files.append_outbox(root, speech(1, body="different"))

    def test_append_refuses_a_seq_that_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files.append_outbox(root, speech(1))
            with self.assertRaises(ProtocolError):
                files.append_outbox(root, speech(3))


class FindCabinetTests(unittest.TestCase):
    def test_walks_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files.room_path(root).parent.mkdir(parents=True)
            files.room_path(root).write_text("{}", encoding="utf-8")
            deep = root / "a" / "b"
            deep.mkdir(parents=True)
            self.assertEqual(files.find_cabinet(deep), root)
            self.assertEqual(files.find_cabinet(root), root)

    def test_no_cabinet_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProtocolError):
                files.find_cabinet(Path(tmp) / "nowhere")


class UtcNowTests(unittest.TestCase):
    def test_shape(self) -> None:
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", files.utc_now()))


if __name__ == "__main__":
    unittest.main()
