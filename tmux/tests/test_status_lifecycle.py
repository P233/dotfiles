import fcntl
import os
import signal
import struct
import termios
import time
import unittest

import test_shortcuts


@unittest.skipUnless(test_shortcuts.TMUX, "tmux is not installed")
class StatusLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.terminal = test_shortcuts.ShortcutTerminalTests()
        self.addCleanup(self.terminal.doCleanups)
        self.terminal.setUp()
        self.terminal.prepare_status_widgets(trace=True)
        self.terminal.wait_for(lambda: len(self.running()) == 4)

    def running(self):
        jobs = {}
        for line in (self.terminal.home / "status-starts").read_text().splitlines():
            name, value = line.split()
            pid = int(value)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            jobs[pid] = name
        return jobs

    def test_replacing_the_command_stops_old_jobs_and_reloading_is_idempotent(self):
        terminal = self.terminal
        original = self.running()
        terminal.tmux("source-file", str(test_shortcuts.CONFIG))
        time.sleep(0.3)
        self.assertEqual(self.running(), original)
        status = terminal.tmux("show-option", "-gv", "status-right").strip()
        terminal.tmux("set-option", "-g", "status-right",
                      status.replace("usage.py --watch", "usage.py  --watch"))
        terminal.wait_for(lambda: not (original.keys() & self.running().keys()))
        terminal.wait_for(lambda: sorted(self.running().values()) ==
                          ["cpu.sh", "focus.py", "ram.sh", "usage.py"])

    def test_removing_the_timer_stops_it_before_the_warning_window(self):
        terminal = self.terminal
        binary = terminal.home / "bin/osascript"
        binary.write_text('#!/bin/sh\necho called >> "$HOME/reminder-calls"\n')
        binary.chmod(0o755)
        terminal.tmux("set-option", "-g", "@focus-started-at", str(int(time.time()) - 3057))
        status = terminal.tmux("show-option", "-gv", "status-right").strip()
        without_timer = status.split(" #[fg=#b0b0bd]| #[range=control|3]")[0]
        terminal.tmux("set-option", "-g", "status-right", without_timer)
        terminal.wait_for(lambda: "focus.py" not in self.running().values())
        time.sleep(4)
        self.assertFalse((terminal.home / "reminder-calls").exists())

    def test_narrowing_stops_only_metrics_and_widening_starts_them_again(self):
        terminal = self.terminal
        original = self.running()
        retained = {pid: name for pid, name in original.items() if name.endswith(".py")}
        for width in (100, 180):
            fcntl.ioctl(terminal.master, termios.TIOCSWINSZ,
                        struct.pack("HHHH", 50, width, 0, 0))
            terminal.client.send_signal(signal.SIGWINCH)
            terminal.wait_for(lambda: terminal.tmux("list-clients", "-F", "#{client_width}").strip()
                              == str(width))
            if width == 100:
                terminal.wait_for(lambda: self.running() == retained)
            else:
                terminal.wait_for(lambda: len(self.running()) == 4)
                self.assertEqual({pid: name for pid, name in self.running().items()
                                  if name.endswith(".py")}, retained)

    def test_session_status_off_stops_jobs(self):
        terminal = self.terminal
        terminal.tmux("set-option", "-t", "shortcuts", "status", "off")
        terminal.wait_for(lambda: not self.running())

    def test_removing_jobs_from_an_additional_status_row_stops_them(self):
        terminal = self.terminal
        status = terminal.tmux("show-option", "-gv", "status-right").strip()
        terminal.tmux("set-option", "-g", "status", "2")
        terminal.tmux("set-option", "-g", "status-format[1]", status)
        terminal.tmux("set-option", "-g", "status-format[0]", "tabs")
        terminal.wait_for(lambda: len(self.running()) == 4)
        terminal.tmux("set-option", "-g", "status-format[1]", "no producers")
        terminal.wait_for(lambda: not self.running())


if __name__ == "__main__":
    unittest.main()
