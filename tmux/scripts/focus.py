#!/usr/bin/python3
"""Render the repeating 52/17 timer; tmux owns its single start timestamp."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time


FOCUS_SECONDS = 52 * 60
BREAK_SECONDS = 17 * 60
BAR_WIDTH = 12
WARNING_SECONDS = 60
REMINDER_MIN_SECONDS = 55
WARNING_COLOR = "#f1fa8c"
ERROR_LOG_BYTES = 4096


def phase(started_at, now):
    cycle, elapsed = divmod(max(0, int(now) - started_at), FOCUS_SECONDS + BREAK_SECONDS)
    if elapsed < FOCUS_SECONDS:
        return "Focus", FOCUS_SECONDS, FOCUS_SECONDS - elapsed, cycle
    return "Break", BREAK_SECONDS, FOCUS_SECONDS + BREAK_SECONDS - elapsed, cycle


def render(started_at, now):
    label, duration, remaining, _ = phase(started_at, now)
    warning = label == "Focus" and remaining <= WARNING_SECONDS
    color = WARNING_COLOR if warning else "#50fa7b" if label == "Focus" else "#b0b0bd"
    track_color = WARNING_COLOR if warning else "#ffffff"
    minutes, seconds = divmod(remaining, 60)
    filled = round(remaining * BAR_WIDTH / duration)
    text = f" {minutes:02d}:{seconds:02d}".ljust(BAR_WIDTH)
    return (f"#[nobold,fg={color}]{label} "
            f"#[fg=#282a36,bg={color}]{text[:filled]}"
            f"#[fg={track_color},bg=#21222c]{text[filled:]}#[default]")


def notify_if_due(started_at, now, reminded_cycle=None):
    """Attempt a due reminder once locally; return the last attempted cycle."""
    label, _, remaining, cycle = phase(started_at, now)
    if (label != "Focus" or not REMINDER_MIN_SECONDS <= remaining <= WARNING_SECONDS
            or cycle == reminded_cycle):
        return reminded_cycle
    token = f"{started_at}:{cycle}:{label}"
    condition = (f"#{{&&:#{{==:#{{@focus-started-at}},{started_at}}},"
                 f"#{{!=:#{{@focus-notified-phase}},{token}}}}}")
    deadline = started_at + cycle * (FOCUS_SECONDS + BREAK_SECONDS) + FOCUS_SECONDS
    command = shlex.join([sys.executable, str(Path(__file__).resolve()),
                          "--remind", str(deadline)]).replace("#", "##")
    # The server checks and claims the phase without yielding between commands.
    # A restarted timer rejects an old job; all clients share the same claim.
    action = (f"set-option -g @focus-notified-phase {shlex.quote(token)} ; "
              f"run-shell -b {shlex.quote(command)}")
    try:
        subprocess.run(["tmux", "if-shell", "-F", condition, action], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError) as error:
        report_failure("focus notification could not be scheduled", error)
    return cycle


def utf8_prefix(text, limit):
    """Return at most limit UTF-8 bytes, dropping a character split by the limit."""
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def report_failure(context, error):
    details = getattr(error, "stderr", "") or ""
    if isinstance(details, bytes):
        details = details.decode("utf-8", errors="replace")
    message = f"{time.strftime('%Y-%m-%d %H:%M:%S %z')} {context}: {error}\n{details}"
    print(message, file=sys.stderr)
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    path = cache / "tmux-focus/reminder-error.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(utf8_prefix(message, ERROR_LOG_BYTES))
                handle.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        notice = f"Focus reminder failed; details: {path}"
    except OSError as log_error:
        print(f"could not save focus reminder error: {log_error}", file=sys.stderr)
        notice = "Focus reminder failed; error log unavailable"
    try:
        subprocess.run(["tmux", "display-message", "-d", "5000", notice.replace("#", "##")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass  # Scheduling failures can mean the tmux server itself is unavailable.


def show_reminder(deadline):
    script = Path(__file__).with_name("focus-reminder.applescript")
    try:
        subprocess.run(["osascript", str(script), str(deadline - WARNING_SECONDS),
                        str(deadline - REMINDER_MIN_SECONDS)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        # A handled failure exits successfully so run-shell does not open view mode.
        report_failure("focus reminder failed", error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("started_at", nargs="?", type=int, help="tmux's start timestamp")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--restart", action="store_true", help="restart at 52 minutes of focus")
    action.add_argument("--remind", type=int, metavar="DEADLINE", help=argparse.SUPPRESS)
    action.add_argument("--watch", action="store_true", help="publish the timer every second")
    args = parser.parse_args()
    if args.remind is not None:
        if args.started_at is not None:
            parser.error("--remind does not take a start timestamp")
        show_reminder(args.remind)
    elif args.restart:
        if args.started_at is not None:
            parser.error("--restart does not take a timestamp")
        subprocess.run(["tmux", "set-option", "-g", "@focus-started-at", str(int(time.time()))],
                       check=True)
    elif args.started_at is None:
        parser.error("a start timestamp is required for status rendering")
    else:
        reminded_cycle = None
        while True:
            now = time.time()
            print(render(args.started_at, now), flush=True)
            reminded_cycle = notify_if_due(args.started_at, now, reminded_cycle)
            if not args.watch:
                break
            # Align with wall-clock seconds; resume derives time instead of catching up ticks.
            time.sleep(max(0.01, 1 - time.time() % 1))


if __name__ == "__main__":
    main()
