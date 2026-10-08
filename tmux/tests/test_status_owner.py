import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pty
import shlex
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tmux/scripts/usage.py"
TMUX = shutil.which("tmux")
spec = importlib.util.spec_from_file_location("usage_status_owner", SCRIPT)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


class StatusOwnerTests(unittest.TestCase):
    def test_an_already_orphaned_watcher_does_not_start_work(self):
        with patch.object(usage.os, "getppid", return_value=1), \
                patch.object(usage, "read_cache", side_effect=AssertionError("started work")):
            usage.watch()


@unittest.skipUnless(TMUX, "tmux is not installed")
class StatusOwnerTerminalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tmux-status-owner-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name).resolve()
        self.socket = self.home / "server.sock"
        self.environment = {**os.environ, "HOME": str(self.home),
                            "XDG_CACHE_HOME": str(self.home / "cache"),
                            "TERM": "xterm-256color"}
        self.environment.pop("TMUX", None)
        self.master = None
        self.client = None
        self.server = None
        self.watcher = None
        self.pane = None
        self.addCleanup(self.stop_processes)
        self.cache = self.home / "cache/tmux-usage"
        self.cache.mkdir(parents=True)
        now = time.time()
        self.data = {"attempted_at": now, "updated_at": now,
                     "windows": {"5h": {"remaining": 50, "resets_at": None}}}
        for provider in ("codex", "claude"):
            (self.cache / f"{provider}.json").write_text(json.dumps(self.data))
        script = self.home / "usage.py"
        shutil.copy2(SCRIPT, script)
        wrapper = self.home / "watch"
        wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$$" > "$HOME/watcher.pid"\n'
                           'exec /usr/bin/python3 "$HOME/usage.py" --watch\n')
        wrapper.chmod(0o755)
        binary = self.home / ".local/bin/codexbar"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/usr/bin/python3\nimport os, time\nfrom pathlib import Path\n"
                          "(Path.home() / 'probe-pids').write_text(f'{os.getppid()} {os.getpid()}')\n"
                          "time.sleep(60)\n")
        binary.chmod(0o755)
        self.tmux("-f", "/dev/null", "new-session", "-d", "-s", "owner",
                  "-x", "180", "-y", "40", "/bin/sh")
        self.server = int(self.tmux("display-message", "-p", "#{pid}"))
        self.pane = int(self.tmux("display-message", "-p", "#{pane_pid}"))
        self.tmux("set-option", "-g", "default-shell", "/bin/sh")
        self.tmux("set-option", "-g", "status-interval", "1")
        self.tmux("set-option", "-g", "status-right-length", "130")
        self.tmux("set-option", "-g", "status-right", f"#({shlex.quote(str(wrapper))})")
        self.master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 180, 0, 0))
            self.client = subprocess.Popen(
                [TMUX, "-S", str(self.socket), "attach-session", "-t", "owner"],
                stdin=slave, stdout=slave, stderr=slave, env=self.environment,
                start_new_session=True,
            )
        finally:
            os.close(slave)
        os.set_blocking(self.master, False)
        self.output = b""
        self.assertTrue(self.wait_for(lambda: b"Codex" in self.output))
        self.watcher = int((self.home / "watcher.pid").read_text())
        parent = subprocess.run(["/bin/ps", "-p", str(self.watcher), "-o", "ppid="],
                                capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(int(parent), self.server)

    def tmux(self, *arguments):
        return subprocess.run([TMUX, "-S", str(self.socket), *arguments],
                              env=self.environment, capture_output=True, text=True,
                              timeout=5, check=True).stdout.strip()

    @staticmethod
    def alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.master is not None:
                try:
                    while True:
                        data = os.read(self.master, 65536)
                        if not data:
                            break
                        self.output = (self.output + data)[-65536:]
                except (BlockingIOError, OSError):
                    pass
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()

    def probe_pids(self):
        path = self.home / "probe-pids"
        return [int(pid) for pid in path.read_text().split()] if path.exists() else []

    def make_query_due(self):
        data = {**self.data, "attempted_at": time.time() - usage.REFRESH_SECONDS - 1}
        temporary = self.cache / "next.json"
        temporary.write_text(json.dumps(data))
        temporary.replace(self.cache / "codex.json")

    def stop_processes(self):
        subprocess.run([TMUX, "-S", str(self.socket), "kill-server"],
                       env=self.environment, capture_output=True)
        if self.watcher is None and (self.home / "watcher.pid").exists():
            self.watcher = int((self.home / "watcher.pid").read_text())
        if self.watcher is not None and self.alive(self.watcher):
            os.kill(self.watcher, signal.SIGTERM)
            self.wait_for(lambda: not self.alive(self.watcher), timeout=4)
        for pid in [self.watcher, self.pane, *self.probe_pids()]:
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if self.client is not None:
            try:
                self.client.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.client.kill()
                self.client.wait(timeout=3)
        if self.master is not None:
            os.close(self.master)

    def test_server_crash_stops_watcher_before_a_later_query_is_due(self):
        os.kill(self.server, signal.SIGKILL)
        self.make_query_due()
        stopped = self.wait_for(lambda: not self.alive(self.watcher))
        self.assertEqual(self.probe_pids(), [], "queried after the server crashed")
        self.assertTrue(stopped, "watcher outlived its tmux server")

    def test_server_crash_cleans_up_an_inflight_query(self):
        self.make_query_due()
        self.assertTrue(self.wait_for(lambda: len(self.probe_pids()) == 2))
        pids = [self.watcher, *self.probe_pids()]
        os.kill(self.server, signal.SIGKILL)
        self.assertTrue(self.wait_for(lambda: all(not self.alive(pid) for pid in pids)),
                        "watcher or query outlived its tmux server")
