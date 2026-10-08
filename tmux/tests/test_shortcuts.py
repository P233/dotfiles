import fcntl
import json
import os
from pathlib import Path
import pty
import re
import shlex
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tmux/tmux.conf"
TMUX = shutil.which("tmux")


def shortcut_sequences():
    sequences = {}
    for line in (ROOT / "ghostty/config").read_text().splitlines():
        if line.startswith("keybind = ") and "=csi:" in line:
            trigger, sequence = line.removeprefix("keybind = ").split("=csi:", 1)
            sequences[trigger] = "\x1b[" + sequence
    return sequences


class ShortcutMappingTests(unittest.TestCase):
    def test_every_forwarded_sequence_has_one_bound_tmux_user_key(self):
        config = CONFIG.read_text()
        keys = re.findall(r'set -s user-keys\[(\d+)\] "\\e\[([^"\n]+)"', config)
        bound = re.findall(r'^bind -n User(\d+) ', config, re.MULTILINE)
        self.assertEqual(len(keys), len(set(index for index, _ in keys)))
        self.assertEqual(len(keys), len(set(sequence for _, sequence in keys)))
        self.assertEqual(len(bound), len(set(bound)))
        self.assertEqual(set(bound), {index for index, _ in keys})
        self.assertEqual(set(shortcut_sequences().values()),
                         {"\x1b[" + sequence for _, sequence in keys})

    def test_physical_digit_aliases_send_the_same_sequence_as_their_digits(self):
        sequences = shortcut_sequences()
        aliases = {trigger: sequence for trigger, sequence in sequences.items()
                   if trigger.startswith("super+digit_")}
        self.assertTrue(aliases)
        for trigger, sequence in aliases.items():
            with self.subTest(trigger=trigger):
                self.assertEqual(sequence, sequences[trigger.replace("digit_", "")])


@unittest.skipUnless(TMUX, "tmux is not installed")
class ShortcutTerminalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tmux-shortcuts-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name).resolve()
        scripts = self.home / ".config/tmux/scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(ROOT / "tmux/scripts/status-jobs.py", scripts / "status-jobs.py")
        self.socket = self.home / "server.sock"
        self.cwd = self.home / "work with 'quotes'"
        self.cwd.mkdir()
        self.environment = {**os.environ, "HOME": str(self.home), "TERM": "xterm-ghostty"}
        self.environment.pop("TMUX", None)
        self.client = None
        self.master = None
        self.addCleanup(self.stop_server)
        self.tmux("-f", str(CONFIG), "new-session", "-d", "-s", "shortcuts",
                  "-c", str(self.cwd), "-x", "180", "-y", "50", "/bin/sh")
        self.tmux("set-option", "-g", "default-shell", "/bin/sh")
        self.tmux("set-option", "-g", "status-right", "")
        self.tmux("set-hook", "-g", "client-session-changed[151]",
                  "set-option -g @test-status-ready yes")
        self.master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 180, 0, 0))
            self.client = subprocess.Popen(
                [TMUX, "-S", str(self.socket), "attach-session", "-t", "shortcuts"],
                stdin=slave, stdout=slave, stderr=slave,
                env=self.environment, start_new_session=True,
            )
        finally:
            os.close(slave)
        os.set_blocking(self.master, False)
        self.output = b""
        self.wait_for(lambda: self.tmux("list-clients", "-F", "#{client_session}").strip()
                      == "shortcuts")
        self.wait_for(lambda: self.tmux("show-option", "-gqv", "@test-status-ready").strip()
                      == "yes")
        self.tmux("set-hook", "-gu", "client-session-changed[151]")
        self.sequences = shortcut_sequences()

    def stop_server(self):
        subprocess.run([TMUX, "-S", str(self.socket), "kill-server"],
                       env=self.environment, capture_output=True)
        if self.client is not None:
            try:
                self.client.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.client.kill()
                self.client.wait(timeout=3)
        if self.master is not None:
            os.close(self.master)

    def tmux(self, *arguments):
        return subprocess.run([TMUX, "-S", str(self.socket), *arguments],
                              env=self.environment, capture_output=True, text=True,
                              timeout=5, check=True).stdout

    def drain(self):
        while True:
            try:
                data = os.read(self.master, 65536)
                if not data:
                    return
                self.output = (self.output + data)[-65536:]
            except (BlockingIOError, OSError):
                return

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.drain()
            if predicate():
                return
            time.sleep(0.02)
        self.fail("tmux did not reach the expected terminal state")

    def send(self, text):
        self.drain()
        self.output = b""
        os.write(self.master, text.encode())
        # Separate keypresses as a keyboard does, rather than simulate paste.
        time.sleep(0.05)
        self.drain()

    def press(self, trigger):
        self.send(self.sequences[trigger])

    def value(self, format_string):
        return self.tmux("display-message", "-p", "-t", "shortcuts", format_string).strip()

    def panes(self):
        return self.tmux("list-panes", "-s", "-t", "shortcuts", "-F", "#{pane_id}").splitlines()

    def windows(self):
        return self.tmux("list-windows", "-t", "shortcuts", "-F", "#{window_id}").splitlines()

    def prepare_status_widgets(self, trace=False):
        scripts = self.home / ".config/tmux/scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        for name in ("usage.py", "focus.py", "cpu.sh", "ram.sh"):
            shutil.copy2(ROOT / "tmux/scripts" / name, scripts / name)
            if trace:
                script = scripts / name
                real = scripts / (name + ".real")
                script.rename(real)
                script.write_text(f'#!/bin/sh\nprintf "%s %s\\n" {shlex.quote(name)} "$$" '
                                  f'>> "$HOME/status-starts"\nexec {shlex.quote(str(real))} "$@"\n')
                script.chmod(0o755)
        cache = self.home / "cache/tmux-usage"
        cache.mkdir(parents=True)
        now = int(time.time())
        data = {"attempted_at": now, "updated_at": now, "windows": {
            "5h": {"remaining": 50, "resets_at": now + 3600},
            "7d": {"remaining": 75, "resets_at": now + 86400},
        }}
        (cache / "codex.json").write_text(json.dumps({**data, "credits": 850}))
        (cache / "claude.json").write_text(json.dumps(data))
        self.tmux("set-environment", "-g", "XDG_CACHE_HOME", str(cache.parent))
        binary = self.home / "bin/open"
        binary.parent.mkdir()
        binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$HOME/opened-urls"\n')
        binary.chmod(0o755)
        self.tmux("set-environment", "-g", "PATH", f"{binary.parent}:{os.environ['PATH']}")
        self.tmux("source-file", str(CONFIG))
        self.wait_for(lambda: b"Codex" in self.output and b"Claude" in self.output
                      and b"Focus" in self.output)

    def click_status(self, column):
        self.send(f"\x1b[<0;{column};1M")
        self.send(f"\x1b[<0;{column};1m")

    def test_redraw_and_timer_reset_do_not_restart_collectors_and_detach_stops_jobs(self):
        self.prepare_status_widgets(trace=True)
        starts = self.home / "status-starts"
        self.wait_for(lambda: len(starts.read_text().splitlines()) == 4)
        initial = starts.read_text().splitlines()
        self.output = b""
        for _ in range(4):
            self.tmux("rename-window", str(time.time()))
            time.sleep(1.05)
            self.drain()
        self.assertEqual(starts.read_text().splitlines(), initial)
        self.tmux("focus-restart")
        self.wait_for(lambda: len(starts.read_text().splitlines()) == 5)
        self.assertTrue(starts.read_text().splitlines()[-1].startswith("focus.py "))
        pids = [int(line.split()[1]) for line in starts.read_text().splitlines()]
        self.tmux("detach-client")

        def all_stopped():
            for pid in pids:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                return False
            return True

        self.wait_for(all_stopped)

    def test_status_widget_clicks_open_exact_urls_after_resizing(self):
        self.prepare_status_widgets()
        opened = self.home / "opened-urls"
        expected = []
        for width in (180, 100):
            with self.subTest(width=width):
                fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", 50, width, 0, 0))
                self.client.send_signal(signal.SIGWINCH)
                self.wait_for(lambda: self.tmux("list-clients", "-F", "#{client_width}").strip()
                              == str(width))
                # Right-aligned: timer 18, Claude 32, Codex 22 (including credits), separators 3.
                claude = width - 18 - 3 - 32 + 1
                codex = claude - 3 - 22
                for column, url in (
                        (codex, "https://chatgpt.com/settings/usage?tab=overview"),
                        (codex + 6, "https://chatgpt.com/settings/usage?tab=overview"),
                        (codex + 21, "https://chatgpt.com/settings/usage?tab=overview"),
                        (claude, "https://claude.ai/new#settings/usage"),
                        (claude + 7, "https://claude.ai/new#settings/usage"),
                        (claude + 31, "https://claude.ai/new#settings/usage")):
                    self.click_status(column)
                    expected.append(url)
                    self.wait_for(lambda: opened.exists() and opened.read_text().splitlines() == expected)
                    time.sleep(0.35)
                # Separator clicks do not inherit the preceding widget's action.
                self.click_status(claude - 2)
                self.click_status(width - 19)
                time.sleep(0.35)
                self.assertEqual(opened.read_text().splitlines(), expected)

    def test_timer_restarts_on_single_click_and_tabs_still_select_windows(self):
        self.prepare_status_widgets()
        for column in (163, 180):
            with self.subTest(column=column):
                old = int(time.time()) - 3200
                self.tmux("set-option", "-g", "@focus-started-at", str(old))
                self.wait_for(lambda: b"Break" in self.output)
                before = int(time.time())
                self.click_status(column)
                self.wait_for(lambda: int(self.tmux("show-option", "-gv", "@focus-started-at")) >= before)
                self.wait_for(lambda: b"Focus" in self.output)
                self.assertFalse((self.home / "opened-urls").exists())
                time.sleep(0.4)
        self.tmux("new-window", "-t", "shortcuts", "/bin/sh")
        self.click_status(2)
        self.wait_for(lambda: self.value("#{window_index}") == "1")

    def test_failed_focus_reminder_reports_details_without_entering_view_mode(self):
        self.prepare_status_widgets()
        binary = self.home / "bin/osascript"
        binary.write_text('#!/bin/sh\necho called >> "$HOME/reminder-calls"\n'
                          'echo native-reminder-fixture-error >&2\nexit 7\n')
        binary.chmod(0o755)
        self.output = b""
        self.tmux("set-option", "-g", "@focus-started-at", str(int(time.time()) - 3060))
        error_log = self.home / "cache/tmux-focus/reminder-error.log"
        self.wait_for(error_log.exists)
        self.wait_for(lambda: b"Focus reminder failed" in self.output)
        self.assertIn("native-reminder-fixture-error", error_log.read_text())
        self.assertEqual(self.value("#{pane_in_mode}"), "0")
        for _ in range(2):
            self.tmux("refresh-client", "-S")
            time.sleep(0.1)
        self.assertEqual((self.home / "reminder-calls").read_text().splitlines(), ["called"])

    def test_splits_inherit_directory_and_pane_navigation_reaches_neighbors(self):
        left = self.value("#{pane_id}")
        self.press("super+d")
        self.wait_for(lambda: len(self.panes()) == 2)
        right = self.value("#{pane_id}")
        self.assertGreater(int(self.value("#{pane_left}")), 0)
        self.assertEqual(self.value("#{pane_current_path}"), str(self.cwd))
        self.press("super+shift+d")
        self.wait_for(lambda: len(self.panes()) == 3)
        bottom = self.value("#{pane_id}")
        self.assertGreater(int(self.value("#{pane_top}")), 0)
        self.assertEqual(self.value("#{pane_current_path}"), str(self.cwd))
        for trigger, target in [("super+[", right), ("super+]", bottom),
                                ("super+alt+arrow_up", right),
                                ("super+alt+arrow_left", left),
                                ("super+alt+arrow_right", right),
                                ("super+alt+arrow_down", bottom)]:
            self.press(trigger)
            self.wait_for(lambda: self.value("#{pane_id}") == target)

    def test_resize_equalize_and_zoom_change_the_actual_layout(self):
        left = self.value("#{pane_id}")
        self.press("super+d")
        self.tmux("select-pane", "-t", left)
        width = int(self.value("#{pane_width}"))
        self.press("super+ctrl+arrow_right")
        self.wait_for(lambda: int(self.value("#{pane_width}")) == width + 10)
        self.press("super+ctrl+arrow_left")
        self.wait_for(lambda: int(self.value("#{pane_width}")) == width)
        self.press("super+t")
        top = self.value("#{pane_id}")
        self.press("super+shift+d")
        self.tmux("select-pane", "-t", top)
        height = int(self.value("#{pane_height}"))
        self.press("super+ctrl+arrow_down")
        self.wait_for(lambda: int(self.value("#{pane_height}")) == height + 10)
        self.press("super+ctrl+arrow_up")
        self.wait_for(lambda: int(self.value("#{pane_height}")) == height)
        self.press("super+ctrl+arrow_down")
        self.press("super+ctrl+=")
        self.wait_for(lambda: int(self.value("#{pane_height}")) == height)
        self.press("super+shift+enter")
        self.wait_for(lambda: self.value("#{window_zoomed_flag}") == "1")
        self.press("super+shift+enter")
        self.wait_for(lambda: self.value("#{window_zoomed_flag}") == "0")

    def test_tabs_use_current_directory_and_native_last_tab_semantics(self):
        self.press("super+t")
        self.wait_for(lambda: self.value("#{window_index}") == "2")
        self.assertEqual(self.value("#{pane_current_path}"), str(self.cwd))
        self.press("super+t")
        self.wait_for(lambda: self.value("#{window_index}") == "3")
        for trigger, index in [("super+shift+[", "2"), ("super+shift+]", "3"),
                               ("ctrl+shift+tab", "2"), ("ctrl+tab", "3"),
                               ("super+1", "1"), ("super+2", "2")]:
            self.press(trigger)
            self.wait_for(lambda: self.value("#{window_index}") == index)
        self.tmux("move-window", "-s", "shortcuts:3", "-t", "shortcuts:7")
        self.press("super+9")
        self.wait_for(lambda: self.value("#{window_index}") == "7")

    def test_pane_close_can_be_cancelled_and_keeps_its_original_target(self):
        self.press("super+d")
        self.press("super+shift+d")
        target = self.value("#{pane_id}")
        self.press("super+w")
        self.wait_for(lambda: b"Close pane" in self.output)
        self.assertEqual(len(self.panes()), 3)
        self.send("n")
        self.assertIn(target, self.panes())
        self.press("super+w")
        self.wait_for(lambda: b"Close pane" in self.output)
        other = next(pane for pane in self.panes() if pane != target)
        self.tmux("select-pane", "-t", other)
        self.send("y")
        self.wait_for(lambda: len(self.panes()) == 2)
        self.assertNotIn(target, self.panes())
        self.assertIn(other, self.panes())

    def test_closing_a_tab_renumbers_digit_shortcuts_without_changing_windows(self):
        self.press("super+t")
        second = self.value("#{window_id}")
        self.press("super+t")
        third = self.value("#{window_id}")
        panes = self.tmux("list-panes", "-t", third, "-F", "#{pane_id}:#{pane_pid}")
        self.press("super+1")
        self.press("super+alt+w")
        self.wait_for(lambda: b"Close tab" in self.output)
        self.tmux("select-window", "-t", third)
        self.send("y")
        self.wait_for(lambda: self.windows() == [second, third])
        self.assertEqual(self.tmux("list-windows", "-t", "shortcuts", "-F",
                                   "#{window_index}").splitlines(), ["1", "2"])
        self.assertEqual(self.value("#{window_id}"), third)
        self.assertEqual(self.tmux("list-panes", "-t", third, "-F", "#{pane_id}:#{pane_pid}"), panes)
        for trigger, window in (("super+1", second), ("super+2", third), ("super+9", third)):
            self.press(trigger)
            self.wait_for(lambda: self.value("#{window_id}") == window)
        self.press("super+t")
        self.wait_for(lambda: self.value("#{window_index}") == "3")

    def test_tab_close_keeps_its_original_target_after_switching_tabs(self):
        self.press("super+t")
        self.press("super+d")
        target = self.value("#{window_id}")
        self.press("super+alt+w")
        self.wait_for(lambda: b"Close tab" in self.output)
        self.tmux("select-window", "-t", "shortcuts:1")
        self.send("y")
        self.wait_for(lambda: len(self.windows()) == 1)
        self.assertNotIn(target, self.windows())
        self.assertEqual(len(self.panes()), 1)

    def test_closing_the_last_pane_ends_only_the_fixture_session(self):
        self.press("super+w")
        self.wait_for(lambda: b"Close pane" in self.output)
        self.send("y")
        self.assertEqual(self.client.wait(timeout=3), 0)

    def test_reload_preserves_default_prefix_and_user_key_indexes(self):
        self.tmux("bind-key", "u", "display-message", "former usage menu")
        self.tmux("bind-key", "U", "display-message", "plugin update")
        for _ in range(2):
            self.tmux("source-file", str(CONFIG))
            self.tmux("set-option", "-g", "status-right", "")
        prefix_keys = [line.split()[3] for line in
                       self.tmux("list-keys", "-T", "prefix").splitlines()]
        self.assertNotIn("u", prefix_keys)
        self.assertIn("U", prefix_keys)
        keys = self.tmux("show-options", "-s", "user-keys").splitlines()
        self.assertEqual(len(keys), len(set(shortcut_sequences().values())))
        self.assertEqual(self.tmux("show-options", "-gv", "prefix").strip(), "C-b")
        self.press("super+d")
        self.wait_for(lambda: len(self.panes()) == 2)
        self.send("\x02")
        self.send("%")
        self.wait_for(lambda: len(self.panes()) == 3)

    def test_usage_refresh_requires_prefix_and_dispatches_without_arguments(self):
        helper = self.home / ".config/tmux/scripts/refresh-usage.sh"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('#!/bin/sh\nprintf "%s\\n" "$#" > "$HOME/usage-refresh"\n')
        helper.chmod(0o755)
        ready = self.home / "ready"
        received = self.home / "received"
        refresh = self.home / "usage-refresh"
        code = ("import os,tty,time; from pathlib import Path; tty.setraw(0); "
                f"Path({str(ready)!r}).touch(); "
                f"Path({str(received)!r}).write_bytes(os.read(0,1)); time.sleep(5)")
        self.tmux("respawn-pane", "-k", "-t", self.value("#{pane_id}"),
                  "/usr/bin/python3 -c " + shlex.quote(code))
        self.wait_for(ready.exists)
        self.send("\x12")
        self.wait_for(lambda: received.exists() and received.read_bytes() == b"\x12")
        self.assertFalse(refresh.exists())
        self.send("\x02")
        self.send("\x12")
        self.wait_for(lambda: refresh.exists() and refresh.read_text().strip() == "0")


if __name__ == "__main__":
    unittest.main()
