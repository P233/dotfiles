import importlib.util
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/focus.py"
REMINDER = SCRIPT.with_name("focus-reminder.applescript")
TMUX = shutil.which("tmux")
NOW = 1_800_000_000
spec = importlib.util.spec_from_file_location("tmux_focus", SCRIPT)
focus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(focus)


def visible(text):
    return re.sub(r"#\[[^]]*\]", "", text)


class FocusDisplayTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("osacompile"), "AppleScript compiler is not installed")
    def test_native_reminder_compiles(self):
        with tempfile.TemporaryDirectory(prefix="tmux-reminder-") as directory:
            subprocess.run(["osacompile", "-o", str(Path(directory) / "reminder.scpt"),
                            str(REMINDER)], check=True, capture_output=True, text=True,
                           timeout=10)

    @unittest.skipUnless(shutil.which("osascript"), "AppleScript runner is not installed")
    def test_native_reminder_skips_a_late_deadline_without_waiting_five_seconds(self):
        now = int(time.time())
        subprocess.run(["osascript", str(REMINDER), str(now - 55), str(now - 50)],
                       check=True, capture_output=True, text=True, timeout=3)

    def test_phase_boundaries_and_repeated_cycles(self):
        for elapsed, expected in ((0, "Focus 52:00"), (1, "Focus 51:59"),
                                  (3119, "Focus 00:01"), (3120, "Break 17:00"),
                                  (4139, "Break 00:01"), (4140, "Focus 52:00"),
                                  (4141, "Focus 51:59"),
                                  (4140 * 100 + 3120, "Break 17:00")):
            with self.subTest(elapsed=elapsed):
                label, _, countdown = expected.partition(" ")
                self.assertEqual(visible(focus.render(NOW, NOW + elapsed)),
                                 f"{label}  {countdown}      ")

    def test_remaining_fill_and_phase_colors_match_quota_bar_style(self):
        for elapsed, label, color, countdown, filled in (
                (0, "Focus", "#50fa7b", "52:00", 12),
                (1560, "Focus", "#50fa7b", "26:00", 6),
                (3119, "Focus", "#f1fa8c", "00:01", 0),
                (3120, "Break", "#b0b0bd", "17:00", 12),
                (3630, "Break", "#b0b0bd", "08:30", 6),
                (4139, "Break", "#b0b0bd", "00:01", 0)):
            with self.subTest(elapsed=elapsed):
                rendered = focus.render(NOW, NOW + elapsed)
                text = f" {countdown}".ljust(12)
                track_color = "#f1fa8c" if label == "Focus" and countdown == "00:01" else "#ffffff"
                self.assertEqual(rendered,
                                 f"#[nobold,fg={color}]{label} "
                                 f"#[fg=#282a36,bg={color}]{text[:filled]}"
                                 f"#[fg={track_color},bg=#21222c]{text[filled:]}#[default]")

    def test_digits_change_color_at_the_fill_boundary_without_moving(self):
        for elapsed, label, color, left, right in (
                (2340, "Focus", "#50fa7b", " 13", ":00      "),
                (3885, "Break", "#b0b0bd", " 04", ":15      ")):
            with self.subTest(label=label):
                rendered = focus.render(NOW, NOW + elapsed)
                self.assertIn(f"#[fg=#282a36,bg={color}]{left}"
                              f"#[fg=#ffffff,bg=#21222c]{right}", rendered)
                self.assertEqual(len(visible(rendered)), 18)

    def test_backward_clock_does_not_wrap_into_a_break(self):
        self.assertEqual(visible(focus.render(NOW, NOW - 10)), "Focus  52:00      ")

    def test_last_minute_highlights_only_focus_label_and_digits(self):
        for deadline, normal in ((3120, "#50fa7b"), (4140, "#b0b0bd")):
            for remaining in (61, 60, 1):
                with self.subTest(deadline=deadline, remaining=remaining):
                    output = focus.render(NOW, NOW + deadline - remaining)
                    warning = deadline == 3120 and remaining <= 60
                    color = "#f1fa8c" if warning else normal
                    foreground = "#f1fa8c" if warning else "#ffffff"
                    self.assertTrue(output.startswith(f"#[nobold,fg={color}]"))
                    self.assertIn(f"#[fg={foreground},bg=#21222c]", output)
                    self.assertEqual(len(visible(output)), 18)
        self.assertTrue(focus.render(NOW, NOW + 4140).startswith("#[nobold,fg=#50fa7b]"))

    def test_failed_schedule_is_attempted_once_locally_until_the_next_cycle(self):
        failure = subprocess.TimeoutExpired("tmux", 3)
        with mock.patch.object(focus.subprocess, "run", side_effect=failure) as schedule, \
                mock.patch.object(focus, "report_failure") as report:
            reminded_cycle = None
            for elapsed in (3059, 3060, 3061, 3065, 3066, 4080):
                reminded_cycle = focus.notify_if_due(NOW, NOW + elapsed, reminded_cycle)
            self.assertEqual(reminded_cycle, 0)
            self.assertEqual(schedule.call_count, 1)
            self.assertEqual(report.call_count, 1)
            reminded_cycle = focus.notify_if_due(NOW, NOW + 4140 + 3060, reminded_cycle)
            self.assertEqual(reminded_cycle, 1)
            self.assertEqual(schedule.call_count, 2)

    def test_error_log_byte_limit_preserves_complete_utf8_characters(self):
        with tempfile.TemporaryDirectory(prefix="tmux-focus-log-") as directory, \
                mock.patch.dict(os.environ, {"XDG_CACHE_HOME": directory}), \
                mock.patch.object(focus.time, "strftime", return_value="timestamp"), \
                mock.patch.object(focus.subprocess, "run"), mock.patch("sys.stderr"):
            error = subprocess.CalledProcessError(7, "osascript", stderr="界" * 2000)
            focus.report_failure("test", error)
            path = Path(directory) / "tmux-focus/reminder-error.log"
            data = path.read_bytes()
            prefix = f"timestamp test: {error}\n"
            expected_characters = (4096 - len(prefix.encode("utf-8"))) // 3
            self.assertEqual(data.decode("utf-8"), prefix + "界" * expected_characters)
            self.assertLessEqual(len(data), 4096)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


@unittest.skipUnless(TMUX, "tmux is not installed")
class FocusTmuxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tmux-focus-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name).resolve()
        (self.home / ".config").mkdir()
        (self.home / ".config/tmux").symlink_to(ROOT, target_is_directory=True)
        self.socket = self.home / "server.sock"
        self.environment = {**os.environ, "HOME": str(self.home),
                            "XDG_CACHE_HOME": str(self.home / "cache")}
        self.environment.pop("TMUX", None)
        self.addCleanup(self.stop_server)
        self.tmux("-f", "/dev/null", "new-session", "-d", "-s", "focus-test", "/bin/sh")
        self.tmux("source-file", str(ROOT / "tmux.conf"))

    def tmux(self, *arguments):
        return subprocess.run([TMUX, "-S", str(self.socket), *arguments],
                              env=self.environment, capture_output=True, text=True,
                              check=True, timeout=5).stdout

    def stop_server(self):
        subprocess.run([TMUX, "-S", str(self.socket), "kill-server"],
                       env=self.environment, capture_output=True, timeout=5)

    def started_at(self):
        return int(self.tmux("show-option", "-gv", "@focus-started-at"))

    def test_initial_load_starts_focus_and_reload_preserves_progress(self):
        self.assertLessEqual(abs(self.started_at() - int(time.time())), 5)
        self.tmux("set-option", "-g", "@focus-started-at", str(NOW))
        for _ in range(2):
            self.tmux("source-file", str(ROOT / "tmux.conf"))
            self.assertEqual(self.started_at(), NOW)
        aliases = self.tmux("show-options", "-s", "command-alias")
        self.assertEqual(aliases.count("focus-restart="), 1)

    def test_restart_command_replaces_break_with_a_full_focus_for_all_sessions(self):
        self.tmux("new-session", "-d", "-s", "second", "/bin/sh")
        self.tmux("set-option", "-g", "@focus-started-at", str(int(time.time()) - 3120))
        self.assertTrue(visible(focus.render(self.started_at(), time.time())).startswith("Break"))
        before = int(time.time())
        output = self.tmux("focus-restart")
        started = self.started_at()
        self.assertEqual(output, "")
        self.assertGreaterEqual(started, before)
        self.assertLessEqual(started, int(time.time()))
        for session in ("focus-test", "second"):
            self.assertEqual(int(self.tmux("show-option", "-Av", "-t", session,
                                           "@focus-started-at")), started)
        self.assertEqual(visible(focus.render(started, started)), "Focus  52:00      ")

    def test_status_job_uses_the_server_timestamp_and_is_the_last_widget(self):
        status = self.tmux("show-option", "-gv", "status-right").strip()
        self.assertTrue(status.endswith("TMUX_STATUS_KIND=focus ~/.config/tmux/scripts/focus.py --watch #{q:@focus-started-at})#[norange]"))
        command = self.tmux("display-message", "-p",
                            "~/.config/tmux/scripts/focus.py #{q:@focus-started-at}").strip()
        result = subprocess.run(["/bin/sh", "-c", command], env=self.environment,
                                capture_output=True, text=True, check=True, timeout=5)
        self.assertTrue(visible(result.stdout).startswith("Focus  5"))
        self.assertIn("#[fg=#282a36,bg=#50fa7b]", result.stdout)
        self.assertEqual(result.stderr, "")

    def prepare_notifications(self):
        binary = self.home / "bin/osascript"
        binary.parent.mkdir()
        binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/notifications"\n')
        binary.chmod(0o755)
        self.environment["PATH"] = f"{binary.parent}:{os.environ['PATH']}"
        self.tmux("set-environment", "-g", "PATH", self.environment["PATH"])
        socket = self.tmux("display-message", "-p", "#{socket_path},#{pid},0").strip()
        patch = mock.patch.dict(os.environ, {"TMUX": socket, "HOME": str(self.home),
                                            "XDG_CACHE_HOME": str(self.home / "cache")})
        patch.start()
        self.addCleanup(patch.stop)
        self.tmux("set-option", "-g", "@focus-started-at", str(NOW))

    def notifications(self, count):
        path = self.home / "notifications"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            lines = path.read_text().splitlines() if path.exists() else []
            if len(lines) >= count:
                self.assertEqual(len(lines), count)
                return lines
            time.sleep(0.02)
        self.fail("notification command was not dispatched")

    def test_focus_reminder_is_shared_once_per_cycle_and_break_stays_silent(self):
        self.prepare_notifications()
        self.tmux("new-session", "-d", "-s", "second", "/bin/sh")
        focus.notify_if_due(NOW, NOW + 3059)
        self.assertFalse((self.home / "notifications").exists())
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda now: focus.notify_if_due(NOW, now), [NOW + 3060] * 8))
        command = self.notifications(1)[0]
        self.assertEqual(command, f"{REMINDER} {NOW + 3060} {NOW + 3065}")
        self.tmux("source-file", str(ROOT / "tmux.conf"))
        focus.notify_if_due(NOW, NOW + 3119)
        focus.notify_if_due(NOW, NOW + 4080)
        focus.notify_if_due(NOW, NOW + 4139)
        self.assertEqual(len(self.notifications(1)), 1)
        focus.notify_if_due(NOW, NOW + 4140 + 3060)
        self.assertEqual(self.notifications(2)[1], f"{REMINDER} {NOW + 7200} {NOW + 7205}")

    def test_a_late_first_update_does_not_replay_the_one_minute_reminder(self):
        self.prepare_notifications()
        for remaining in (61, 54, 5, 1, 0):
            focus.notify_if_due(NOW, NOW + 3120 - remaining)
        self.assertEqual(self.tmux("show-option", "-gqv", "@focus-notified-phase"), "")
        self.assertFalse((self.home / "notifications").exists())
        focus.notify_if_due(NOW, NOW + 3120 - 55)
        self.notifications(1)

    def test_restart_rejects_an_old_warning_and_allows_the_new_timer(self):
        self.prepare_notifications()
        focus.notify_if_due(NOW, NOW + 3060)
        self.notifications(1)
        restarted = NOW + 3060
        self.tmux("set-option", "-g", "@focus-started-at", str(restarted))
        focus.notify_if_due(NOW, NOW + 4140 + 3060)
        focus.notify_if_due(restarted, restarted + 3059)
        self.assertEqual(len(self.notifications(1)), 1)
        focus.notify_if_due(restarted, restarted + 3060)
        self.assertEqual(self.notifications(2)[1], f"{REMINDER} {restarted + 3060} {restarted + 3065}")

    def test_status_command_keeps_error_details_and_renders_when_tmux_is_unavailable(self):
        self.prepare_notifications()
        started = int(time.time()) - 3061
        self.tmux("set-option", "-g", "@focus-started-at", str(started))
        environment = {**self.environment, "TMUX": os.environ["TMUX"]}
        result = subprocess.run([str(SCRIPT), str(started)], env=environment,
                                capture_output=True, text=True, check=True, timeout=5)
        self.assertIn("#[fg=#f1fa8c,bg=#21222c]", result.stdout)
        self.assertEqual(result.stderr, "")
        self.notifications(1)
        environment["TMUX"] = f"{self.home}/missing.sock,0,0"
        result = subprocess.run([str(SCRIPT), str(started)], env=environment,
                                capture_output=True, text=True, check=True, timeout=5)
        self.assertIn("#[fg=#f1fa8c,bg=#21222c]", result.stdout)
        self.assertIn("focus notification could not be scheduled", result.stderr)
        error_log = self.home / "cache/tmux-focus/reminder-error.log"
        self.assertIn("error connecting to", error_log.read_text())
        self.assertIn("missing.sock", error_log.read_text())
        self.assertEqual(error_log.stat().st_mode & 0o777, 0o600)

    def test_reminder_failure_keeps_only_one_bounded_error_log(self):
        self.prepare_notifications()
        binary = self.home / "bin/osascript"
        binary.write_text('#!/bin/sh\nprintf "native reminder failed: test detail\\n" >&2\nexit 7\n')
        environment = {**self.environment, "TMUX": os.environ["TMUX"]}
        result = subprocess.run([str(SCRIPT), "--remind", str(int(time.time()) + 60)],
                                env=environment, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        error_log = self.home / "cache/tmux-focus/reminder-error.log"
        self.assertIn("native reminder failed: test detail", error_log.read_text())
        self.assertIn("exit status 7", error_log.read_text())
        binary.write_text('#!/bin/sh\n/usr/bin/yes long-error | /usr/bin/head -c 20000 >&2\nexit 8\n')
        subprocess.run([str(SCRIPT), "--remind", str(int(time.time()) + 60)],
                       env=environment, capture_output=True, text=True, check=True, timeout=5)
        self.assertLessEqual(error_log.stat().st_size, 4096)
        self.assertIn("exit status 8", error_log.read_text())
        self.assertNotIn("test detail", error_log.read_text())
        self.assertEqual(list(error_log.parent.iterdir()), [error_log])


if __name__ == "__main__":
    unittest.main()
