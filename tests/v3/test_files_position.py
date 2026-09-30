from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tincan import files
from tincan.types import MemberId, Position, ProtocolError, Seq

CAROL = MemberId("carol")
ALBINA = MemberId("albina")


class ParseTests(unittest.TestCase):
    def test_two_columns(self) -> None:
        pos = files.parse_position(ALBINA, "carol 4\nalbina 2\n")
        self.assertEqual(pos.me, "albina")
        self.assertEqual(pos.seen, {"carol": 4, "albina": 2})

    def test_blank_lines_are_ignored(self) -> None:
        pos = files.parse_position(ALBINA, "\ncarol 4\n\n")
        self.assertEqual(pos.seen, {"carol": 4})

    def test_empty_file_is_no_cursor(self) -> None:
        self.assertEqual(files.parse_position(ALBINA, "").seen, {})

    def test_bad_lines_die(self) -> None:
        for raw in ("carol\n", "carol 4 5\n", "carol x\n", "carol -1\n", " 4\n"):
            with self.subTest(raw=raw):
                with self.assertRaises(ProtocolError):
                    files.parse_position(ALBINA, raw)

    def test_duplicate_writer_dies(self) -> None:
        with self.assertRaises(ProtocolError):
            files.parse_position(ALBINA, "carol 4\ncarol 5\n")


class FormatTests(unittest.TestCase):
    def test_sorted_two_columns(self) -> None:
        pos = Position(ALBINA, {CAROL: Seq(4), ALBINA: Seq(2)})
        self.assertEqual(files.format_position(pos), "albina 2\ncarol 4\n")

    def test_empty_cursor_is_an_empty_file(self) -> None:
        self.assertEqual(files.format_position(Position(ALBINA, {})), "")

    def test_round_trip(self) -> None:
        pos = Position(ALBINA, {CAROL: Seq(4), ALBINA: Seq(2)})
        self.assertEqual(files.parse_position(ALBINA, files.format_position(pos)), pos)


class DiskTests(unittest.TestCase):
    def test_missing_file_is_no_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pos = files.load_position(Path(tmp), ALBINA)
            self.assertEqual(pos.me, "albina")
            self.assertEqual(pos.seen, {})

    def test_write_then_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = files.write_position(root, Position(ALBINA, {CAROL: Seq(4)}))
            self.assertEqual(path, files.pos_path(root, ALBINA))
            self.assertEqual(path.read_text(encoding="utf-8"), "carol 4\n")
            self.assertEqual(files.load_position(root, ALBINA).seen, {"carol": 4})

    def test_rewrite_replaces_the_whole_file_and_leaves_no_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files.write_position(root, Position(ALBINA, {CAROL: Seq(4), ALBINA: Seq(9)}))
            files.write_position(root, Position(ALBINA, {CAROL: Seq(5)}))
            path = files.pos_path(root, ALBINA)
            self.assertEqual(path.read_text(encoding="utf-8"), "carol 5\n")
            self.assertEqual([p.name for p in path.parent.iterdir()], ["albina"])

    def test_rename_source_shares_the_target_directory(self) -> None:
        seen: list[tuple[str, str]] = []
        real = os.replace

        def spy(src, dst, **kwargs):
            seen.append((str(src), str(dst)))
            return real(src, dst, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            os.replace = spy
            try:
                files.write_position(Path(tmp), Position(ALBINA, {CAROL: Seq(1)}))
            finally:
                os.replace = real
        self.assertEqual(len(seen), 1)
        src, dst = seen[0]
        self.assertEqual(Path(src).parent, Path(dst).parent)
        self.assertNotEqual(Path(src).name, Path(dst).name)


if __name__ == "__main__":
    unittest.main()
