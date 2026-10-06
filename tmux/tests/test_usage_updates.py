import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_usage import NOW, NOW_ISO, SCRIPT, summary, usage, window


def iso(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).isoformat()


def used_up_cache(reset=NOW + 3600):
    return {"updated_at": NOW, "attempted_at": NOW, "windows": usage.quota_windows({
        "primary": window(300, 100, resetsAt=iso(reset)),
    })}


def native_payload(used=37, reset=NOW + 3600):
    return {"session_id": "private-session", "transcript_path": "private-transcript",
            "rate_limits": {"five_hour": {"used_percentage": used, "resets_at": reset},
                            "seven_day": {"used_percentage": 21, "resets_at": NOW + 86400}}}


class UsageUpdateTests(unittest.TestCase):
    def test_a_used_up_codex_window_shows_zero_and_polling_continues(self):
        cache = used_up_cache()
        self.assertEqual(summary(usage.render("codex", cache, NOW)), "Codex 0% 1h")
        self.assertFalse(usage.should_refresh("codex", cache, NOW + 179))
        self.assertTrue(usage.should_refresh("codex", cache, NOW + 180))

    def test_claude_status_reads_never_query_automatically(self):
        for cache in ({}, {"updated_at": NOW, "attempted_at": NOW,
                           "windows": {"5h": {"remaining": 63, "resets_at": None}}},
                      used_up_cache(NOW)):
            with self.subTest(cache=cache), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "claude.json"
                usage.write_cache(path, cache)
                with patch.object(usage.time, "time", return_value=NOW + 86400), \
                        patch.object(usage, "fetch") as fetch:
                    usage.refresh("claude", path)
                    fetch.assert_not_called()

    def test_failed_codex_query_is_retried_after_the_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.json"
            usage.write_cache(path, used_up_cache())
            with patch.object(usage.time, "time", return_value=NOW + 180), \
                    patch.object(usage, "fetch", side_effect=ValueError("private message")) as fetch:
                cache, failure = usage.refresh("codex", path)
                fetch.assert_called_once()
            self.assertEqual(failure, "ValueError")
            self.assertIn("error", cache)
            self.assertFalse(usage.should_refresh("codex", cache, NOW + 359))
            self.assertTrue(usage.should_refresh("codex", cache, NOW + 360))
            self.assertNotIn("private message", path.read_text())

    def test_manual_refresh_queries_claude_and_detects_an_early_reset(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"provider": "claude",
            "usage": {"updatedAt": NOW_ISO, "primary": window(300, 20)}}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            usage.write_cache(path, used_up_cache())
            with patch.object(usage.time, "time", return_value=NOW), \
                    patch.object(usage, "fetch", return_value=result) as fetch:
                usage.refresh("claude", path)
                fetch.assert_not_called()
                cache, failure = usage.refresh("claude", path, force=True)
                fetch.assert_called_once_with("claude")
            self.assertIsNone(failure)
            self.assertEqual(cache["windows"]["5h"]["remaining"], 80)

    def test_a_failed_explicit_refresh_exits_nonzero_and_still_prints_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / ".local/bin/codexbar"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\nexit 3\n")
            binary.chmod(0o755)
            for provider in ("codex", "claude"):
                with self.subTest(provider=provider):
                    result = subprocess.run(
                        [sys.executable, "-B", str(SCRIPT), provider, "--refresh"],
                        capture_output=True, text=True, timeout=10,
                        env={**os.environ, "HOME": str(root), "XDG_CACHE_HOME": str(root / "cache")})
                    self.assertEqual(result.returncode, 1)
                    self.assertTrue(result.stdout.startswith(provider.title()))
                    self.assertIn(f"{provider} query failed", result.stderr)

    def test_idle_claude_retains_last_received_quota_with_a_stale_marker(self):
        cache = {"updated_at": NOW, "windows": {
            "5h": {"remaining": 63, "resets_at": NOW + 7200},
            "7d": {"remaining": 79, "resets_at": NOW + 86400},
        }}
        self.assertEqual(summary(usage.render("claude", cache, NOW + 3600)),
                         "Claude 63%~ 1h 79%~ 23h")

    def test_manual_helper_refreshes_both_providers_before_repainting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / ".config/tmux/scripts"
            scripts.mkdir(parents=True)
            (scripts / "usage.py").write_bytes(SCRIPT.read_bytes())
            binary = root / ".local/bin/codexbar"
            binary.parent.mkdir(parents=True)
            # The background Codex query finishes last, so an early repaint is observable.
            binary.write_text("#!/usr/bin/python3\nimport json,sys,datetime,time\n"
                              "provider=sys.argv[sys.argv.index('--provider')+1]\n"
                              "time.sleep(0.3 if provider == 'codex' else 0)\n"
                              "now=datetime.datetime.now(datetime.timezone.utc)\n"
                              "print(json.dumps({'provider':provider,'usage':{'updatedAt':now.isoformat(),"
                              "'primary':{'usedPercent':23,'windowMinutes':300,"
                              "'resetsAt':(now+datetime.timedelta(hours=2)).isoformat()}}}))\n")
            binary.chmod(0o755)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            tmux = bin_dir / "tmux"
            # The repaint must observe both refreshed caches, not the seeded ones.
            tmux.write_text('#!/bin/sh\nset -e\n'
                            'grep -q \'"remaining": 77\' "$XDG_CACHE_HOME/tmux-usage/codex.json"\n'
                            'grep -q \'"remaining": 77\' "$XDG_CACHE_HOME/tmux-usage/claude.json"\n'
                            'printf "%s\\n" "$*" > "$HOME/repaint"\n')
            tmux.chmod(0o755)
            cache_dir = root / "cache/tmux-usage"
            cache_dir.mkdir(parents=True)
            for provider in ("codex", "claude"):
                cache = used_up_cache()
                cache["updated_at"] = time.time() - 1
                usage.write_cache(cache_dir / f"{provider}.json", cache)
            helper = SCRIPT.with_name("refresh-usage.sh")
            subprocess.run(["sh", str(helper)], check=True, capture_output=True,
                           text=True, timeout=5, env={**os.environ, "HOME": str(root),
                               "XDG_CACHE_HOME": str(root / "cache"),
                               "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
            for provider in ("codex", "claude"):
                self.assertEqual(usage.read_cache(cache_dir / f"{provider}.json")
                                 ["windows"]["5h"]["remaining"], 77)
            self.assertEqual((root / "repaint").read_text().strip(), "refresh-client -S")

    def test_native_ingest_sanitizes_data_and_does_not_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            with patch.object(usage.time, "time", return_value=NOW + 1), \
                    patch.object(usage, "fetch") as fetch:
                self.assertTrue(usage.ingest_native(path, native_payload()))
                fetch.assert_not_called()
            cache = usage.read_cache(path)
            self.assertEqual(cache["windows"]["5h"]["remaining"], 63)
            self.assertEqual(cache["windows"]["7d"]["remaining"], 79)
            self.assertNotIn("private", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_repeated_native_snapshot_cannot_erase_an_early_manual_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            payload = native_payload(used=100)
            with patch.object(usage.time, "time", return_value=NOW):
                usage.ingest_native(path, payload)
            # An early reset starts a new five-hour period with a later deadline.
            row = {"provider": "claude", "usage": {
                "updatedAt": NOW_ISO, "primary": window(300, 20, resetsAt=iso(NOW + 18000)),
                "secondary": window(10080, 21, resetsAt=iso(NOW + 86400))}}
            with patch.object(usage.time, "time", return_value=NOW), \
                    patch.object(usage, "fetch", return_value=subprocess.CompletedProcess([], 0, json.dumps(row))):
                usage.refresh("claude", path, force=True)
            original = path.read_bytes()
            with patch.object(usage.time, "time", return_value=NOW + 60):
                self.assertFalse(usage.ingest_native(path, payload))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(usage.read_cache(path)["windows"]["5h"]["remaining"], 80)
            with patch.object(usage.time, "time", return_value=NOW + 61):
                self.assertTrue(usage.ingest_native(path, native_payload(used=21, reset=NOW + 18000)))
            self.assertEqual(usage.read_cache(path)["windows"]["5h"]["remaining"], 79)

    def test_an_older_native_snapshot_cannot_replace_newer_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            # Interleaved sessions: A, newer B, A again, then a repeat of B.
            for offset, used, accepted in ((0, 10, True), (60, 40, True), (120, 10, False), (180, 40, False)):
                with patch.object(usage.time, "time", return_value=NOW + offset):
                    self.assertEqual(usage.ingest_native(path, native_payload(used=used)), accepted)
            self.assertEqual(usage.read_cache(path)["windows"]["5h"]["remaining"], 60)
            # A later reset deadline starts a new period, even with more quota remaining.
            with patch.object(usage.time, "time", return_value=NOW + 240):
                self.assertTrue(usage.ingest_native(path, native_payload(used=5, reset=NOW + 18000)))
            self.assertEqual(usage.read_cache(path)["windows"]["5h"]["remaining"], 95)

    def test_a_rounded_manual_deadline_still_names_the_native_period(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            usage.write_cache(path, {"updated_at": NOW, "windows": {
                "5h": {"remaining": 40, "resets_at": NOW + 3600 + 59},
                "7d": {"remaining": 79, "resets_at": NOW + 86400}}})
            for used, accepted, remaining in ((20, False, 40), (70, True, 30)):
                with patch.object(usage.time, "time", return_value=NOW + 60):
                    self.assertEqual(usage.ingest_native(path, native_payload(used=used)), accepted)
                self.assertEqual(usage.read_cache(path)["windows"]["5h"]["remaining"], remaining)

    def test_a_snapshot_without_a_deadline_replaces_a_different_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            usage.write_cache(path, {"updated_at": NOW, "windows": {
                "5h": {"remaining": 60, "resets_at": NOW - 10}}})
            payload = {"rate_limits": {"five_hour": {"used_percentage": 30}}}
            with patch.object(usage.time, "time", return_value=NOW + 60):
                self.assertTrue(usage.ingest_native(path, payload))
            self.assertEqual(summary(usage.render("claude", usage.read_cache(path), NOW + 60)),
                             "Claude 70% — — —")

    def test_a_newer_snapshot_refreshes_its_unchanged_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            with patch.object(usage.time, "time", return_value=NOW):
                usage.ingest_native(path, native_payload(used=20))
            with patch.object(usage.time, "time", return_value=NOW + 600):
                self.assertTrue(usage.ingest_native(path, native_payload(used=30)))
            self.assertEqual(summary(usage.render("claude", usage.read_cache(path), NOW + 600)),
                             "Claude 70% 50m 79% 23h")

    def test_missing_or_invalid_native_fields_keep_the_last_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.json"
            usage.write_cache(path, used_up_cache())
            original = path.read_bytes()
            for payload in (None, [], {}, {"rate_limits": None},
                            {"rate_limits": {"five_hour": {"used_percentage": True}}},
                            {"rate_limits": {"five_hour": {"used_percentage": 10 ** 400}}},
                            {"rate_limits": {"five_hour": {"used_percentage": 101}}}):
                with self.subTest(payload=payload):
                    self.assertFalse(usage.ingest_native(path, payload))
                    self.assertEqual(path.read_bytes(), original)

    def test_partial_native_snapshot_updates_only_the_reported_windows(self):
        previous = {"5h": {"remaining": 80, "resets_at": NOW + 3600},
                    "7d": {"remaining": 90, "resets_at": NOW + 86400}}
        for missing, field, expected in (("5h", "five_hour", "Claude 80%~ 50m 79% 23h"),
                                         ("7d", "seven_day", "Claude 63% 50m 90%~ 23h")):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "claude.json"
                usage.write_cache(path, {"updated_at": NOW, "windows": previous})
                payload = native_payload()
                del payload["rate_limits"][field]
                with patch.object(usage.time, "time", return_value=NOW + 600):
                    self.assertTrue(usage.ingest_native(path, payload))
                cache = usage.read_cache(path)
                self.assertEqual(cache["windows"][missing]["remaining"], previous[missing]["remaining"])
                # The omitted window keeps its own ten-minute-old measurement time.
                self.assertEqual(summary(usage.render("claude", cache, NOW + 600)), expected)

    def test_native_callback_is_silent_and_malformed_input_is_harmless(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "XDG_CACHE_HOME": directory}
            for payload in (json.dumps(native_payload()), "{invalid", "{}"):
                result = subprocess.run([sys.executable, "-B", str(SCRIPT), "claude", "--ingest"],
                                        input=payload, capture_output=True, text=True, env=env,
                                        timeout=3, check=True)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
            self.assertNotIn("private", (Path(directory) / "tmux-usage/claude.json").read_text())

    def test_native_callback_is_silent_when_cache_directory_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked = Path(directory) / "blocked"
            blocked.touch()
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "claude", "--ingest"],
                                    input=json.dumps(native_payload()), capture_output=True,
                                    text=True, timeout=3,
                                    env={**os.environ, "XDG_CACHE_HOME": str(blocked)})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_native_update_during_query_wins_over_an_older_result_or_failure(self):
        for failing in (False, True):
            with self.subTest(failing=failing), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "tmux-usage/claude.json"
                path.parent.mkdir()
                usage.write_cache(path, {"updated_at": NOW - 60,
                                         "windows": usage.native_windows(native_payload(used=10))})

                def fetch(_provider):
                    # A separate callback must finish while the query is still running.
                    code = ("import runpy,sys,time; "
                            f"time.time=lambda: {NOW + 5}; "
                            f"sys.argv=[{str(SCRIPT)!r},'claude','--ingest']; "
                            f"runpy.run_path({str(SCRIPT)!r},run_name='__main__')")
                    subprocess.run([sys.executable, "-B", "-c", code],
                                   input=json.dumps(native_payload()), capture_output=True,
                                   text=True, check=True, timeout=3,
                                   env={**os.environ, "XDG_CACHE_HOME": directory})
                    if failing:
                        raise ValueError("private failure")
                    return subprocess.CompletedProcess([], 0, json.dumps({"provider": "claude",
                        "usage": {"updatedAt": NOW_ISO, "primary": window(300, 90)}}))

                with patch.object(usage.time, "time", return_value=NOW), \
                        patch.object(usage, "fetch", side_effect=fetch):
                    cache, _ = usage.refresh("claude", path, force=True)
                self.assertEqual(cache["windows"]["5h"]["remaining"], 63)
                self.assertEqual(cache["updated_at"], NOW + 5)
                self.assertNotIn("error", cache)

    def test_query_merges_each_window_around_a_newer_native_update(self):
        deadlines = {"5h": NOW + 7200, "7d": NOW + 86400}
        for label, field, expected in (
                ("5h", "five_hour", "Claude 60% 1h 50%~ 23h"),
                ("7d", "seven_day", "Claude 80%~ 1h 60% 23h")):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "tmux-usage/claude.json"
                path.parent.mkdir()
                usage.write_cache(path, {"updated_at": NOW - 600, "windows": {
                    name: {"remaining": 90, "resets_at": deadline}
                    for name, deadline in deadlines.items()
                }})

                def fetch(_provider):
                    # Only one window changes while the query is in flight.
                    payload = {"rate_limits": {field: {
                        "used_percentage": 40, "resets_at": deadlines[label],
                    }}}
                    code = ("import runpy,sys,time; "
                            f"time.time=lambda: {NOW + 5}; "
                            f"sys.argv=[{str(SCRIPT)!r},'claude','--ingest']; "
                            f"runpy.run_path({str(SCRIPT)!r},run_name='__main__')")
                    subprocess.run([sys.executable, "-B", "-c", code],
                                   input=json.dumps(payload), capture_output=True,
                                   text=True, check=True, timeout=3,
                                   env={**os.environ, "XDG_CACHE_HOME": directory})
                    return subprocess.CompletedProcess([], 0, json.dumps({"provider": "claude",
                        "usage": {"updatedAt": NOW_ISO,
                                  "primary": window(300, 20, resetsAt=iso(deadlines["5h"])),
                                  "secondary": window(10080, 50, resetsAt=iso(deadlines["7d"]))}}))

                with patch.object(usage.time, "time", return_value=NOW), \
                        patch.object(usage, "fetch", side_effect=fetch):
                    cache, failure = usage.refresh("claude", path, force=True)
                self.assertIsNone(failure)
                self.assertEqual(cache, usage.read_cache(path))
                self.assertEqual(cache["updated_at"], NOW + 5)
                # Query data ages from its measurement time, not the newer native callback.
                self.assertEqual(summary(usage.render("claude", cache, NOW + 302)), expected)

    def test_existing_query_lock_prevents_duplicate_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.json"
            with path.with_suffix(".fetch.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(usage, "fetch") as fetch:
                    usage.refresh("codex", path, force=True)
                    fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
