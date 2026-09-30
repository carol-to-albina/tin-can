from __future__ import annotations

import contextlib
import io
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from tincan import wake
from tincan.types import (
    Autonomy,
    EventRef,
    Member,
    MemberId,
    Mode,
    Seq,
    Wake,
    WakeMessage,
    WakeType,
)

NOTE = WakeMessage(
    recipient=MemberId("albina"),
    events=(
        EventRef(MemberId("carol"), Seq(4)),
        EventRef(MemberId("carol"), Seq(5)),
    ),
)


def member(
    wake_type: WakeType = WakeType.HTTP,
    url: str = "",
    key: str = "",
    member_id: str = "albina",
) -> Member:
    return Member(
        id=MemberId(member_id),
        github="enjojoy",
        display="Albina",
        mode=Mode.WEBHOOK,
        autonomy=Autonomy.AUTO,
        latency_sec=86400,
        wake=Wake(wake_type, url, key),
    )


class WakeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.env()

    def env(self, **values: str) -> None:
        patcher = mock.patch.dict(os.environ, values)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in list(os.environ):
            if name.startswith("TINCAN_WAKE_KEY_") and name not in values:
                del os.environ[name]

    def doorbell(self) -> tuple[list[dict[str, str]], str]:
        rung: list[dict[str, str]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                rung.append(
                    {
                        "path": self.path,
                        "auth": self.headers.get("Authorization") or "",
                        "type": self.headers.get("Content-Type") or "",
                        "body": self.rfile.read(length).decode("utf-8"),
                    }
                )
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args: object) -> None:
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return rung, f"http://127.0.0.1:{server.server_address[1]}/wake"


class ResolveKeyTests(WakeCase):
    def test_resolve_key_takes_the_environment_first(self) -> None:
        self.env(TINCAN_WAKE_KEY_ALBINA="env-key")
        self.assertEqual(
            wake.resolve_key(MemberId("albina"), "file-key", False), "env-key"
        )

    def test_resolve_key_uppercases_the_id_and_maps_hyphens(self) -> None:
        self.env(TINCAN_WAKE_KEY_ALBINA_TWO="env-key")
        self.assertEqual(wake.resolve_key(MemberId("albina-two"), "", False), "env-key")

    def test_resolve_key_takes_the_file_key_on_a_private_remote(self) -> None:
        self.assertEqual(
            wake.resolve_key(MemberId("albina"), "file-key", False), "file-key"
        )

    def test_resolve_key_refuses_the_file_key_on_a_public_remote(self) -> None:
        self.assertEqual(wake.resolve_key(MemberId("albina"), "file-key", True), "")

    def test_resolve_key_keeps_the_environment_key_on_a_public_remote(self) -> None:
        self.env(TINCAN_WAKE_KEY_ALBINA="env-key")
        self.assertEqual(
            wake.resolve_key(MemberId("albina"), "file-key", True), "env-key"
        )

    def test_resolve_key_is_empty_when_nothing_is_set(self) -> None:
        self.assertEqual(wake.resolve_key(MemberId("albina"), "", False), "")


class PostHttpTests(WakeCase):
    def test_post_http_sends_the_refs_and_the_bearer_header(self) -> None:
        rung, url = self.doorbell()
        wake.post_http(url, "file-key", NOTE)
        self.assertEqual(len(rung), 1)
        self.assertEqual(rung[0]["path"], "/wake")
        self.assertEqual(rung[0]["auth"], "Bearer file-key")
        self.assertEqual(rung[0]["type"], "application/json")
        self.assertEqual(
            json.loads(rung[0]["body"]),
            {"recipient": "albina", "events": ["carol:4", "carol:5"]},
        )

    def test_post_http_prints_one_line_when_nobody_answers(self) -> None:
        noise = io.StringIO()
        with contextlib.redirect_stderr(noise):
            wake.post_http("http://127.0.0.1:1/wake", "file-key", NOTE)
        lines = noise.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("albina", lines[0])

    def test_post_http_prints_one_line_on_a_bad_url(self) -> None:
        noise = io.StringIO()
        with contextlib.redirect_stderr(noise):
            wake.post_http("not-a-url", "file-key", NOTE)
        self.assertEqual(len(noise.getvalue().splitlines()), 1)


class NotifyMemberTests(WakeCase):
    def test_notify_member_posts_with_the_resolved_key(self) -> None:
        rung, url = self.doorbell()
        self.env(TINCAN_WAKE_KEY_ALBINA="env-key")
        wake.notify_member(member(url=url, key="file-key"), NOTE, False)
        self.assertEqual(len(rung), 1)
        self.assertEqual(rung[0]["auth"], "Bearer env-key")

    def test_notify_member_skips_wake_type_none(self) -> None:
        rung, url = self.doorbell()
        self.env(TINCAN_WAKE_KEY_ALBINA="env-key")
        wake.notify_member(member(WakeType.NONE, url=url), NOTE, False)
        self.assertEqual(rung, [])

    def test_notify_member_skips_a_missing_key(self) -> None:
        rung, url = self.doorbell()
        wake.notify_member(member(url=url), NOTE, False)
        self.assertEqual(rung, [])

    def test_notify_member_skips_a_file_key_on_a_public_remote(self) -> None:
        rung, url = self.doorbell()
        wake.notify_member(member(url=url, key="file-key"), NOTE, True)
        self.assertEqual(rung, [])

    def test_notify_member_skips_a_missing_url(self) -> None:
        rung, _ = self.doorbell()
        self.env(TINCAN_WAKE_KEY_ALBINA="env-key")
        wake.notify_member(member(key="file-key"), NOTE, False)
        self.assertEqual(rung, [])


if __name__ == "__main__":
    unittest.main()
