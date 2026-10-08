import json
import os
from pathlib import Path
import re
import select
import subprocess
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class StatusWatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tmux-watch-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.cache = self.home / "cache/tmux-usage"
        self.cache.mkdir(parents=True)
        self.environment = {**os.environ, "HOME": str(self.home),
                            "XDG_CACHE_HOME": str(self.cache.parent)}
        self.write_cache("codex", 50)
        self.write_cache("claude", 60)

    def write_cache(self, provider, remaining, attempted_at=None):
        now = time.time()
        data = {"updated_at": now, "attempted_at": now if attempted_at is None else attempted_at,
                "windows": {"5h": {"remaining": remaining, "resets_at": now + 3600}}}
        temporary = self.cache / "incoming"
        temporary.write_text(json.dumps(data))
        temporary.replace(self.cache / f"{provider}.json")

    def start(self, script, *arguments):
        process = subprocess.Popen([str(SCRIPTS / script), *arguments], env=self.environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop, process)
        return process

    def stop(self, process):
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)

    def line(self, process, timeout=3):
        ready, _, _ = select.select([process.stdout], [], [], timeout)
        self.assertTrue(ready, "status producer did not publish in time")
        line = process.stdout.readline().decode()
        self.assertTrue(line, process.stderr.read().decode() if process.poll() is not None else "EOF")
        return line

    def test_focus_publishes_seconds_without_restarting(self):
        process = self.start("focus.py", "--watch", str(int(time.time())))
        first = self.line(process)
        second = self.line(process, 1.5)
        third = self.line(process, 1.5)
        self.assertEqual(len({first, second, third}), 3)
        self.assertIsNone(process.poll())

    def test_metrics_publish_every_five_seconds_in_one_process(self):
        processes = [self.start(name, "--watch") for name in ("cpu.sh", "ram.sh")]
        for process in processes:
            self.assertRegex(self.line(process), r"^(CPU|RAM) \d+%\n$")
        self.assertEqual(select.select([p.stdout for p in processes], [], [], 1.2)[0], [])
        for process in processes:
            self.assertRegex(self.line(process, 5), r"^(CPU|RAM) \d+%\n$")
            self.assertIsNone(process.poll())

    def test_slow_codex_does_not_delay_native_claude_and_stops_with_watcher(self):
        binary = self.home / ".local/bin/codexbar"
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\necho $$ > "$HOME/probe-pid"\nexec /bin/sleep 20\n')
        binary.chmod(0o755)
        self.write_cache("codex", 50, attempted_at=0)
        process = self.start("usage.py", "--watch")
        self.assertIn("Claude", self.line(process))
        deadline = time.monotonic() + 3
        while not (self.home / "probe-pid").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.home / "probe-pid").exists())
        probe = int((self.home / "probe-pid").read_text())
        self.write_cache("claude", 23)
        self.assertIn("23%", re.sub(r"#\[[^]]*\]", "", self.line(process)))
        self.assertIsNone(process.poll())
        process.terminate()
        process.wait(timeout=3)
        with self.assertRaises(ProcessLookupError):
            os.kill(probe, 0)

    def test_a_cancelled_query_does_not_delay_the_next_watchers_query(self):
        binary = self.home / ".local/bin/codexbar"
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\necho $$ >> "$HOME/probe-pids"\nexec /bin/sleep 20\n')
        binary.chmod(0o755)
        self.write_cache("codex", 50, attempted_at=0)
        probes = self.home / "probe-pids"

        def probe_count(count):
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if probes.exists() and len(probes.read_text().split()) == count:
                    return True
                time.sleep(0.02)
            return False

        first = self.start("usage.py", "--watch")
        self.assertTrue(probe_count(1))
        first.terminate()
        first.wait(timeout=5)
        cache = json.loads((self.cache / "codex.json").read_text())
        self.assertEqual(cache["attempted_at"], 0)
        self.start("usage.py", "--watch")
        self.assertTrue(probe_count(2), "the replacement watcher waited for the interval")

    def test_unchanged_quota_does_not_republish_or_query(self):
        process = self.start("usage.py", "--watch")
        self.assertIn("Codex", self.line(process))
        self.assertEqual(select.select([process.stdout], [], [], 1.3)[0], [])
        self.write_cache("codex", 27)
        self.assertIn("27%", re.sub(r"#\[[^]]*\]", "", self.line(process)))
        self.assertFalse((self.cache / "codex.fetch.lock").exists())


if __name__ == "__main__":
    unittest.main()
