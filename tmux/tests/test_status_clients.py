import fcntl
import json
import os
import pty
import re
import signal
import struct
import subprocess
import termios
import time
import unittest

import test_shortcuts


@unittest.skipUnless(test_shortcuts.TMUX, "tmux is not installed")
class StatusClientTests(unittest.TestCase):
    def setUp(self):
        self.terminal = test_shortcuts.ShortcutTerminalTests()
        self.addCleanup(self.terminal.doCleanups)
        self.terminal.setUp()
        self.terminal.prepare_status_widgets()
        self.terminal.wait_for(lambda: "status-jobs.py " not in
                               self.terminal.tmux("show-messages", "-J"))
        self.terminal.tmux("new-session", "-d", "-s", "secondary",
                           "-c", str(self.terminal.cwd), "/bin/sh")
        # Attaching also runs the session-change hook; wait for its cleanup before
        # recording process identities, rather than observing its temporary jobs.
        self.terminal.tmux("set-hook", "-g", "client-session-changed[151]",
                           'set-option -gF @status-test-attached "#{hook_client}"')
        self.master, slave = pty.openpty()
        try:
            client_name = os.ttyname(slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 180, 0, 0))
            self.client = subprocess.Popen(
                [test_shortcuts.TMUX, "-S", str(self.terminal.socket),
                 "attach-session", "-t", "secondary"],
                stdin=slave, stdout=slave, stderr=slave,
                env=self.terminal.environment, start_new_session=True,
            )
        finally:
            os.close(slave)
        os.set_blocking(self.master, False)
        self.addCleanup(self.stop_client)
        self.identities = {self.terminal.client.pid: "shortcuts", self.client.pid: "secondary"}
        self.wait_for(lambda: self.terminal.tmux("show-option", "-gqv", "@status-test-attached")
                      .strip() == client_name)
        self.terminal.tmux("set-hook", "-gu", "client-session-changed[151]")
        self.wait_for(lambda: len(self.jobs()) == 8)

    def stop_client(self):
        if self.client.poll() is None:
            self.client.terminate()
        try:
            self.client.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.client.kill()
            self.client.wait(timeout=3)
        os.close(self.master)

    def drain(self):
        self.terminal.drain()
        while True:
            try:
                if not os.read(self.master, 65536):
                    return
            except (BlockingIOError, OSError):
                return

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.drain()
            if predicate():
                return
            time.sleep(0.02)
        self.fail("tmux clients did not reach the expected status state")

    def jobs(self):
        result = set()
        for line in self.terminal.tmux("show-messages", "-J").splitlines():
            match = re.search(
                r"TMUX_STATUS_CLIENT=(\d+) TMUX_STATUS_KIND=(cpu|ram|quota|focus) "
                r".* \[fd=-?\d+, pid=(\d+), status=\d+\]$", line
            )
            if match:
                client, kind, pid = match.groups()
                result.add((int(client), kind, int(pid)))
        return result

    def resize_first_client(self, width):
        fcntl.ioctl(self.terminal.master, termios.TIOCSWINSZ,
                    struct.pack("HHHH", 50, width, 0, 0))
        self.terminal.client.send_signal(signal.SIGWINCH)

    def test_identical_reload_keeps_collectors_after_session_creation_and_closure(self):
        original = self.jobs()
        self.terminal.tmux("source-file", str(test_shortcuts.CONFIG))
        self.wait_for(lambda: len(self.jobs()) == 8)
        self.assertEqual(self.jobs(), original)
        retained = {job for job in original if job[0] == self.terminal.client.pid}
        self.terminal.tmux("kill-session", "-t", "secondary")
        self.wait_for(lambda: self.jobs() == retained)
        self.terminal.tmux("source-file", str(test_shortcuts.CONFIG))
        self.wait_for(lambda: len(self.jobs()) == 4)
        self.assertEqual(self.jobs(), retained)

    def test_rapid_resize_only_replaces_the_resized_clients_metrics(self):
        original = self.jobs()
        first = self.terminal.client.pid
        retained = {job for job in original if job[0] != first or job[1] in ("quota", "focus")}
        for _ in range(2):
            # A queued resize cleanup must recheck the final width before acting.
            for width in (100, 180, 100):
                self.resize_first_client(width)
                time.sleep(0.03)
            self.wait_for(lambda: self.jobs() == retained)
            self.resize_first_client(180)
            self.wait_for(lambda: len(self.jobs()) == 8)
            self.assertEqual({job for job in self.jobs()
                              if job[0] != first or job[1] in ("quota", "focus")}, retained)

    def test_switching_to_a_hidden_status_stops_only_that_clients_jobs(self):
        terminal = self.terminal
        terminal.tmux("new-session", "-d", "-s", "hidden", "/bin/sh")
        terminal.tmux("set-option", "-t", "hidden", "status", "off")
        original = self.jobs()
        first = terminal.client.pid
        retained = {job for job in original if job[0] != first}
        names = terminal.tmux("list-clients", "-F", "#{client_pid} #{client_name}")
        name = next(row.split()[1] for row in names.splitlines()
                    if int(row.split()[0]) == first)
        terminal.tmux("switch-client", "-c", name, "-t", "hidden")
        self.wait_for(lambda: self.jobs() == retained)
        self.assertEqual(len(retained), 4)
        terminal.tmux("switch-client", "-c", name, "-t", "shortcuts")
        self.wait_for(lambda: len(self.jobs()) == 8)
        self.assertEqual({job for job in self.jobs() if job[0] != first}, retained)
        self.assertEqual({kind for client, kind, _ in self.jobs() if client == first},
                         {"cpu", "ram", "quota", "focus"})

    def test_session_status_off_cancels_its_probe_and_keeps_other_client_jobs(self):
        terminal = self.terminal
        binary = terminal.home / ".local/bin/codexbar"
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nprintf "%s %s\\n" "$$" "$PPID" > "$HOME/probe-pids"\n'
                          'exec /bin/sleep 30\n')
        binary.chmod(0o755)
        cache = terminal.home / "cache/tmux-usage/codex.json"
        data = json.loads(cache.read_text())
        data["attempted_at"] = 0
        incoming = cache.with_name("incoming")
        incoming.write_text(json.dumps(data))
        incoming.replace(cache)
        marker = terminal.home / "probe-pids"
        self.wait_for(lambda: marker.exists() and len(marker.read_text().split()) == 2)
        probe, query = map(int, marker.read_text().split())
        watcher = int(subprocess.check_output(
            ["/bin/ps", "-p", str(query), "-o", "ppid="], text=True,
        ).strip())
        original = self.jobs()
        owner = next(client for client, kind, pid in original
                     if kind == "quota" and pid == watcher)
        retained = {job for job in original if job[0] != owner}
        terminal.tmux("set-option", "-t", self.identities[owner], "status", "off")
        self.wait_for(lambda: self.jobs() == retained)

        def probe_stopped():
            try:
                os.kill(probe, 0)
            except ProcessLookupError:
                return True
            return False

        self.wait_for(probe_stopped)
        self.assertEqual(len(retained), 4)
        self.assertEqual(self.jobs(), retained)


if __name__ == "__main__":
    unittest.main()
