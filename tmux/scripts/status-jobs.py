#!/usr/bin/python3
"""Stop tmux-owned status jobs after layout changes or client resizing."""

import argparse
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time


SCRIPTS = {"cpu": "cpu.sh", "ram": "ram.sh", "quota": "usage.py", "focus": "focus.py"}
JOB_ROW = re.compile(r"Job \d+: (.*) \[fd=-?\d+, pid=(-?\d+), status=\d+\]")


def tmux(*arguments):
    return subprocess.run(["tmux", *arguments], check=True, capture_output=True,
                          text=True, timeout=5).stdout


def status_job(row):
    """Recognize only our complete command signatures, never arbitrary shell text."""
    match = JOB_ROW.fullmatch(row)
    if match is None or int(match[2]) <= 1:
        return None
    try:
        args = shlex.split(match[1])
    except ValueError:
        return None
    if args[:2] != ["exec", "env"]:
        return None
    metadata = dict(arg.split("=", 1) for arg in args[2:4] if "=" in arg)
    client = metadata.get("TMUX_STATUS_CLIENT", "")
    kind = metadata.get("TMUX_STATUS_KIND")
    if (not re.fullmatch(r"[0-9]+", client) or int(client) <= 1
            or kind not in SCRIPTS or len(metadata) != 2):
        return None
    script = SCRIPTS[kind]
    paths = {f"~/.config/tmux/scripts/{script}", str(Path(__file__).with_name(script))}
    command = args[4:]
    # Only the timer carries an argument: tmux's start timestamp.
    arity = 3 if kind == "focus" else 2
    if (len(command) != arity or command[0] not in paths or command[1] != "--watch"
            or (kind == "focus" and not re.fullmatch(r"-?\d+", command[2]))):
        return None
    return int(match[2]), client, kind


def clients():
    rows = tmux("list-clients", "-F",
                "#{client_pid} #{client_width} #{session_id} #{q:client_name}")
    result = {}
    for row in rows.splitlines():
        identity, width, session, name = shlex.split(row)
        result[identity] = (int(width), session, name)
    return result


def stop_jobs(targets, metrics_only=False):
    stopped = []
    for row in tmux("show-messages", "-J").splitlines():
        job = status_job(row)
        if job is None:
            continue
        pid, client, kind = job
        if client not in targets:
            continue
        if metrics_only and kind not in ("cpu", "ram"):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except ProcessLookupError:
            pass
    # Allow usage.py's finally block to stop its probe before tmux reaps/restarts it.
    deadline = time.monotonic() + 4
    while stopped and time.monotonic() < deadline:
        remaining = []
        for pid in stopped:
            try:
                os.kill(pid, 0)
                remaining.append(pid)
            except ProcessLookupError:
                pass
        stopped = remaining
        if stopped:
            time.sleep(0.02)
    if stopped:
        raise RuntimeError(f"status jobs did not stop: {stopped}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--layout", action="store_true", help="reload jobs after a layout change")
    mode.add_argument("--narrow", metavar="CLIENT", help="stop metrics if this client is still narrow")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--session", help="limit layout cleanup to a session")
    target.add_argument("--client", help="limit layout cleanup to a client")
    args = parser.parse_args()
    current = clients()
    if args.narrow is not None:
        # Recheck now: a queued resize event may already have been superseded.
        targets = {identity for identity, (width, _, name) in current.items()
                   if name == args.narrow and width < 150}
        if targets:
            stop_jobs(targets, metrics_only=True)
    else:
        targets = {identity for identity, (_, session, name) in current.items()
                   if (args.session is None or session == args.session)
                   and (args.client is None or name == args.client)}
        stop_jobs(targets)
        # Layout edits are infrequent. Ordinary updates and timer resets never force refresh.
        for identity, (_, _, name) in clients().items():
            if identity in targets:
                tmux("refresh-client", "-t", name, "-S")


if __name__ == "__main__":
    main()
