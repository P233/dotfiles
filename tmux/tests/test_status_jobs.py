import importlib.util
from pathlib import Path
import shlex
import signal
import subprocess
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/status-jobs.py"
spec = importlib.util.spec_from_file_location("tmux_status_jobs", SCRIPT)
status_jobs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status_jobs)


def job_row(command, pid=2345):
    return f"Job 0: {command} [fd=12, pid={pid}, status=0]"


def command(kind="cpu", client="1234", path=None):
    if path is None:
        path = f"~/.config/tmux/scripts/{status_jobs.SCRIPTS[kind]}"
    arguments = ["exec", "env", f"TMUX_STATUS_CLIENT={client}",
                 f"TMUX_STATUS_KIND={kind}", path, "--watch"]
    if kind == "focus":
        arguments.append("1800000000")
    return shlex.join(arguments)


class StatusJobParsingTests(unittest.TestCase):
    def test_complete_owned_signatures_accept_each_widget_and_both_paths(self):
        for kind, script in status_jobs.SCRIPTS.items():
            for path in (f"~/.config/tmux/scripts/{script}", str(SCRIPT.with_name(script))):
                with self.subTest(kind=kind, path=path):
                    self.assertEqual(status_jobs.status_job(job_row(command(kind, path=path))),
                                     (2345, "1234", kind))

    def test_metadata_order_and_shell_quoting_do_not_change_identity(self):
        text = ('exec env TMUX_STATUS_KIND=cpu "TMUX_STATUS_CLIENT=1234" '
                '"~/.config/tmux/scripts/cpu.sh" --watch')
        self.assertEqual(status_jobs.status_job(job_row(text)), (2345, "1234", "cpu"))

    def test_watchers_without_client_metadata_are_not_owned(self):
        for kind, script in status_jobs.SCRIPTS.items():
            text = f"~/.config/tmux/scripts/{script} --watch"
            if kind == "focus":
                text += " 1800000000"
            with self.subTest(kind=kind):
                self.assertIsNone(status_jobs.status_job(job_row(text)))

    def test_non_process_pids_and_malformed_job_rows_are_rejected(self):
        for pid in (-1, 0, 1):
            with self.subTest(pid=pid):
                self.assertIsNone(status_jobs.status_job(job_row(command(), pid)))
        for row in ("", job_row(command()) + " trailing", "prefix " + job_row(command()),
                    job_row(command()).replace("pid=2345", "pid=not-a-pid"),
                    job_row(command()).replace("fd=12", "fd=unknown"),
                    job_row(command()).replace("status=0", "status=unknown")):
            with self.subTest(row=row):
                self.assertIsNone(status_jobs.status_job(row))

    def test_shell_compositions_and_unterminated_quotes_are_rejected(self):
        owned = command()
        for text in (f"{owned}; sleep 30", f"{owned} && sleep 30", f"{owned} | cat",
                     f"{owned} &", f"{owned} >/tmp/status", f"echo {owned}",
                     f"sh -c {shlex.quote(owned)}", owned + " '"):
            with self.subTest(command=text):
                self.assertIsNone(status_jobs.status_job(job_row(text)))

    def test_nearby_paths_and_extra_arguments_are_rejected(self):
        for path in ("/tmp/cpu.sh", "~/.config/tmux/scripts/cpu.sh.backup",
                     "~/.config/tmux/scripts/../scripts/cpu.sh", "$HOME/.config/tmux/scripts/cpu.sh"):
            with self.subTest(path=path):
                self.assertIsNone(status_jobs.status_job(job_row(command(path=path))))
        for suffix in (" unexpected", " --watch", " #comment"):
            with self.subTest(suffix=suffix):
                self.assertIsNone(status_jobs.status_job(job_row(command() + suffix)))

    def test_metadata_must_name_the_same_widget_and_only_reserved_keys(self):
        owned = command()
        for text in (owned.replace("TMUX_STATUS_KIND=cpu", "TMUX_STATUS_KIND=ram"),
                     owned.replace("TMUX_STATUS_KIND=cpu", "TMUX_STATUS_KIND=other"),
                     owned.replace("TMUX_STATUS_KIND=cpu", "OTHER=cpu"),
                     owned.replace("TMUX_STATUS_KIND=cpu", "TMUX_STATUS_CLIENT=1234"),
                     owned.replace("exec env ", "env "),
                     owned.replace("exec env ", "exec env EXTRA=value ")):
            with self.subTest(command=text):
                self.assertIsNone(status_jobs.status_job(job_row(text)))

    def test_client_metadata_requires_an_ascii_process_id(self):
        for client in ("", "0", "1", "-2", "12.0", "1;2", "１２３４", "²"):
            with self.subTest(client=client):
                self.assertIsNone(status_jobs.status_job(job_row(command(client=client))))

    def test_focus_requires_exactly_one_integer_start_timestamp(self):
        prefix = command("focus").removesuffix("1800000000")
        for value in ("", "now", "123.5", "123 extra", "--restart"):
            with self.subTest(value=value):
                self.assertIsNone(status_jobs.status_job(job_row(prefix + value)))
        self.assertEqual(status_jobs.status_job(job_row(prefix + "-123")),
                         (2345, "1234", "focus"))


class StatusClientParsingTests(unittest.TestCase):
    def test_empty_client_list_and_escaped_names(self):
        with mock.patch.object(status_jobs, "tmux", return_value=""):
            self.assertEqual(status_jobs.clients(), {})
        rows = "1234 149 $1 /dev/ttys001\n5678 180 $2 client\\ name\n"
        with mock.patch.object(status_jobs, "tmux", return_value=rows):
            self.assertEqual(status_jobs.clients(),
                             {"1234": (149, "$1", "/dev/ttys001"),
                              "5678": (180, "$2", "client name")})

    def test_malformed_client_rows_fail_before_cleanup(self):
        for row in ("1234 180 $1", "1234 wide $1 name", '1234 180 $1 "unterminated',
                    "1234 180 $1 name extra"):
            with self.subTest(row=row), mock.patch.object(status_jobs, "tmux", return_value=row), \
                    mock.patch("sys.argv", [str(SCRIPT), "--layout"]), \
                    mock.patch.object(status_jobs.os, "kill") as kill:
                with self.assertRaises(ValueError):
                    status_jobs.main()
                kill.assert_not_called()

    def test_tmux_errors_are_propagated_without_signalling_processes(self):
        failure = subprocess.CalledProcessError(1, ["tmux", "list-clients"], stderr="no server")
        with mock.patch.object(status_jobs, "tmux", side_effect=failure), \
                mock.patch("sys.argv", [str(SCRIPT), "--layout"]), \
                mock.patch.object(status_jobs.os, "kill") as kill:
            with self.assertRaises(subprocess.CalledProcessError):
                status_jobs.main()
            kill.assert_not_called()


class StatusJobTargetTests(unittest.TestCase):
    def test_metrics_cleanup_only_signals_the_target_clients_owned_metrics(self):
        rows = "\n".join((job_row(command("cpu"), 2345), job_row(command("ram"), 2346),
                          job_row(command("quota"), 2347), job_row(command("focus"), 2348),
                          job_row(command("cpu", client="5678"), 2349),
                          job_row("~/.config/tmux/scripts/cpu.sh --watch", 2350)))
        def kill(_pid, signum):
            if signum == 0:
                raise ProcessLookupError
        with mock.patch.object(status_jobs, "tmux", return_value=rows), \
                mock.patch.object(status_jobs.os, "kill", side_effect=kill) as signals:
            status_jobs.stop_jobs({"1234"}, metrics_only=True)
        self.assertEqual([call.args for call in signals.call_args_list if call.args[1]],
                         [(2345, signal.SIGTERM), (2346, signal.SIGTERM)])


if __name__ == "__main__":
    unittest.main()
