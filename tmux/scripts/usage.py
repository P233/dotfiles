#!/usr/bin/python3
"""Show sanitized, cached subscription quota in the tmux status row."""

import argparse
from contextlib import contextmanager
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "tmux-usage"
BINARY = Path.home() / ".local/bin/codexbar"
SOURCES = {"codex": "oauth", "claude": "cli"}
REFRESH_SECONDS = 180
STALE_SECONDS = 300
EXPIRE_SECONDS = 900
FETCH_TIMEOUT = 25
BAR_WIDTH = 12
# Epoch seconds; the bound also rejects millisecond timestamps.
MAX_EPOCH = 1e12
# Keeps the compact credit balance within seven cells.
MAX_CREDITS = 1e9
# Manual Claude results carry reset times read from the CLI's rounded display.
SAME_PERIOD_SECONDS = 3600
COLORS = {"codex": "#a6c8ff", "claude": "#ffb890"}
# PragmataPro Mono Liga's native one-cell Nerd refresh glyph.
RESET_ICON = "\uf021"


def bounded(value, upper):
    # type() excludes JSON booleans; the comparison rejects NaN and infinities.
    return type(value) in (int, float) and 0 <= value <= upper


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except ValueError:
        return None


def quota_windows(usage):
    """Match actual durations; primary can contain a weekly fallback."""
    windows = {}
    for name in ("primary", "secondary"):
        window = usage.get(name)
        if not isinstance(window, dict) or window.get("isSyntheticPlaceholder"):
            continue
        minutes = window.get("windowMinutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            continue
        label = {300: "5h", 10080: "7d"}.get(minutes)
        measurement = quota_measurement(window.get("usedPercent"), timestamp(window.get("resetsAt")))
        if label is not None and measurement is not None and label not in windows:
            windows[label] = measurement
    return windows


def quota_measurement(used, deadline):
    if not bounded(used, 100):
        return None
    return {"remaining": round(100 - used),
            "resets_at": deadline if bounded(deadline, MAX_EPOCH) else None}


def native_windows(payload):
    rate_limits = payload.get("rate_limits") if isinstance(payload, dict) else None
    if not isinstance(rate_limits, dict):
        return {}
    windows = {}
    for name, label in (("five_hour", "5h"), ("seven_day", "7d")):
        window = rate_limits.get(name)
        if isinstance(window, dict):
            measurement = quota_measurement(window.get("used_percentage"), window.get("resets_at"))
            if measurement is not None:
                windows[label] = measurement
    return windows


def credit_balance(credits):
    if not isinstance(credits, dict) or credits.get("balanceReadSucceeded") is False:
        return None
    remaining = credits.get("remaining")
    return remaining if bounded(remaining, MAX_CREDITS) else None


def valid_window(window):
    # A window's own updated_at overrides the snapshot's when it was kept from an older one.
    return (isinstance(window, dict) and type(window.get("remaining")) is int
            and bounded(window["remaining"], 100)
            and (window.get("resets_at") is None or bounded(window["resets_at"], MAX_EPOCH))
            and ("updated_at" not in window or bounded(window["updated_at"], MAX_EPOCH)))


def valid_cache(cache):
    windows = cache.get("windows", {})
    return (all(bounded(cache.get(key, 0), MAX_EPOCH) for key in ("attempted_at", "updated_at"))
            and isinstance(windows, dict)
            and all(label in ("5h", "7d") and valid_window(window) for label, window in windows.items())
            and bounded(cache.get("credits", 0), MAX_CREDITS)
            and isinstance(cache.get("error", ""), str))


def read_cache(path):
    try:
        cache = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    if not isinstance(cache, dict) or not valid_cache(cache):
        return {}
    sanitized = {key: cache[key] for key in ("attempted_at", "updated_at", "windows", "credits", "error")
                 if key in cache}
    if "windows" in sanitized:
        sanitized["windows"] = {label: {key: window[key] for key in ("remaining", "resets_at", "updated_at")
                                        if key in window}
                                for label, window in sanitized["windows"].items()}
    return sanitized


def should_refresh(provider, cache, now):
    # Claude receives native data, so only a manual refresh queries it.
    return provider == "codex" and now - cache.get("attempted_at", 0) >= REFRESH_SECONDS


def compact_count(value):
    if value < 999.5:
        return f"{value:.0f}"
    if value < 999_950:
        return f"{value / 1e3:.1f}k"
    return f"{value / 1e6:.1f}M"


def render(provider, cache, now):
    updated_at = cache.get("updated_at") or 0
    age = max(0, now - updated_at)
    # Claude retains its last native snapshot while idle; polled Codex data expires.
    retained = provider == "claude" or age <= EXPIRE_SECONDS
    windows = cache.get("windows", {}) if retained else {}

    def progress(label):
        measurement = windows.get(label)
        resets_at = measurement.get("resets_at") if measurement else None
        resetting = resets_at is not None and now >= resets_at
        value = measurement["remaining"] if measurement and not resetting else None
        filled = 0 if value is None else round(value * BAR_WIDTH / 100)
        if resetting:
            percentage = RESET_ICON
        elif value is None:
            percentage = "—"
        else:
            stale = cache.get("error") or now - measurement.get("updated_at", updated_at) > STALE_SECONDS
            percentage = f'{value}%{"~" if stale else ""}'
        if resets_at is None:
            countdown = "—"
        elif resetting:
            countdown = "0m"
        else:
            minutes = math.ceil((resets_at - now) / 60)
            if minutes >= 1440:
                days = minutes // 1440
                countdown = f"{days}d" if days <= 99 else ">99d"
            elif minutes >= 60:
                countdown = f"{minutes // 60}h"
            else:
                countdown = f"{minutes}m"
        text = f" {percentage}".ljust(BAR_WIDTH - len(countdown) - 1) + countdown + " "
        # Bright fills need dark text; the unfilled track keeps white text.
        color = COLORS[provider]
        return (f'#[nobold,fg=#282a36,bg={color}]{text[:filled]}'
                f'#[fg=#ffffff,bg=#21222c]{text[filled:]}#[default]')

    if provider == "claude":
        bars = f'{progress("5h")} {progress("7d")}'
    else:
        # A known 5h window stays selected while its reset awaits fresh data.
        bars = progress("5h" if "5h" in windows else "7d")
        credits = cache.get("credits") if retained else None
        if credits:
            bars += f" #[fg={COLORS[provider]}]{compact_count(credits)}#[default]"
    return f"{provider.title()} {bars}"


def write_cache(path, cache):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(cache, handle)
            handle.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def locked_cache(path):
    # This lock protects short read/modify/write operations, never network requests.
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield read_cache(path)


def supersedes(incoming, cached):
    """Whether one measurement of a window is newer than another."""
    new, old = incoming.get("resets_at"), cached.get("resets_at")
    if new is None or old is None:
        # Without both deadlines the periods cannot be ordered, so arrival order decides.
        return incoming["remaining"] != cached["remaining"]
    if abs(new - old) > SAME_PERIOD_SECONDS:
        # A later deadline starts a new window period; an earlier one belongs to a past period.
        return new > old
    # Usage only grows within a period, so more remaining quota means an older snapshot.
    return incoming["remaining"] < cached["remaining"]


def ingest_native(path, payload):
    # Each Claude session reports its last API response, so snapshots arrive out of order.
    windows = native_windows(payload)
    if not windows:
        return False
    now = time.time()
    with locked_cache(path) as cache:
        cached = cache.get("windows", {})
        newer = {label for label, window in windows.items()
                 if label not in cached or supersedes(window, cached[label])}
        if not newer or now < cache.get("updated_at", 0):
            return False
        # A newer snapshot also confirms its windows that are not older than the cache.
        current = {label: window for label, window in windows.items()
                   if label in newer or not supersedes(cached[label], window)}
        measured_at = cache.get("updated_at", 0)
        kept = {label: {**window, "updated_at": window.get("updated_at", measured_at)}
                for label, window in cached.items() if label not in current}
        write_cache(path, {"updated_at": now, "windows": {**kept, **current}})
    return True


def fetch(provider):
    command = [str(BINARY), "usage", "--provider", provider, "--source", SOURCES[provider],
               "--format", "json", "--json-only"]
    with tempfile.TemporaryDirectory(prefix="tmux-usage-probe-") as cwd:
        with subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, start_new_session=True) as process:
            def stop_probe():
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            def interrupted(signum, _frame):
                stop_probe()
                raise SystemExit(128 + signum)

            signals = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
            previous = {sig: signal.signal(sig, interrupted) for sig in signals}
            try:
                stdout, _ = process.communicate(timeout=FETCH_TIMEOUT)
            except subprocess.TimeoutExpired:
                stop_probe()
                process.communicate()
                raise
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            return subprocess.CompletedProcess(command, process.returncode, stdout)


def parse_usage(provider, result):
    """Return the sanitized measurement in a CodexBar result or raise ValueError."""
    payload = json.loads(result.stdout)
    rows = payload if isinstance(payload, list) else [payload]
    row = next((row for row in rows if isinstance(row, dict) and row.get("provider") == provider), None)
    if row is None:
        raise ValueError("provider row is missing")
    if result.returncode or row.get("error"):
        raise ValueError(f"provider fetch failed (exit {result.returncode})")
    usage = row.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("quota payload is not an object")
    updated_at = timestamp(usage.get("updatedAt"))
    if updated_at is None:
        raise ValueError("quota measurement has no timestamp")
    windows = quota_windows(usage)
    if not windows:
        raise ValueError("quota measurement has no supported windows")
    measurement = {"updated_at": updated_at, "windows": windows}
    credits = credit_balance(row.get("credits")) if provider == "codex" else None
    if credits is not None:
        measurement["credits"] = credits
    return measurement


def refresh(provider, path, force=False):
    """Query when due or forced; return the resulting cache and this query's error name."""
    # The lock is released by the OS even if tmux terminates this status job.
    with path.with_suffix(".fetch.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return read_cache(path), None
        now = time.time()
        with locked_cache(path) as cache:
            if not force and not should_refresh(provider, cache, now):
                return cache, None
            previous_attempt = cache.get("attempted_at", 0)
            cache["attempted_at"] = now
            write_cache(path, cache)
        error_name = None
        try:
            incoming = {"attempted_at": now, **parse_usage(provider, fetch(provider))}
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            # Persist no account identities, credentials, raw output, or provider messages.
            error_name = type(error).__name__
        except SystemExit:
            # A stopped status producer cancelled this query; its replacement may retry now.
            with locked_cache(path) as latest:
                latest["attempted_at"] = previous_attempt
                write_cache(path, latest)
            raise
        with locked_cache(path) as latest:
            if error_name:
                # A native update arriving during a failed query remains valid.
                if latest.get("updated_at", 0) <= cache.get("updated_at", 0):
                    latest["error"] = error_name
                    write_cache(path, latest)
                return latest, error_name
            measured_at = incoming["updated_at"]
            latest_at = latest.get("updated_at", 0)
            if measured_at >= latest_at:
                write_cache(path, incoming)
                return incoming, None
            # A newer native snapshot can still contain older or missing windows.
            windows = latest.get("windows", {})
            updates = {label: {**window, "updated_at": measured_at}
                       for label, window in incoming["windows"].items()
                       if label not in windows
                       or measured_at >= windows[label].get("updated_at", latest_at)}
            if updates:
                latest["windows"] = {**windows, **updates}
                write_cache(path, latest)
            return latest, None


def watch():
    """Publish both quotas; a separate query process cannot stall native updates."""
    owner = os.getppid()
    probe = None
    next_probe = 0
    previous_line = None

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    signals = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
    previous_handlers = {sig: signal.signal(sig, interrupted) for sig in signals}
    try:
        while True:
            # A quiet output pipe cannot reveal that the owning tmux server died.
            if owner == 1 or os.getppid() != owner:
                break
            now = time.time()
            caches = {provider: read_cache(CACHE_DIR / f"{provider}.json")
                      for provider in SOURCES}
            # tmux.conf binds MouseDown1Control1/2 to these ranges.
            line = (f'#[range=control|1,fg={COLORS["codex"]}]'
                    f'{render("codex", caches["codex"], now)}#[norange] '
                    f'#[fg=#b0b0bd]| #[range=control|2,fg={COLORS["claude"]}]'
                    f'{render("claude", caches["claude"], now)}#[norange]')
            if line != previous_line:
                print(line, flush=True)
                previous_line = line
            if probe is not None and probe.poll() is not None:
                probe = None
            if (probe is None and now >= next_probe
                    and should_refresh("codex", caches["codex"], now)):
                # Keep the CLI's existing cache locks, timeout and signal cleanup.
                # The local bound also prevents a failed child startup from spinning.
                next_probe = now + REFRESH_SECONDS
                probe = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "codex"],
                                         stdout=subprocess.DEVNULL)
            time.sleep(1)
    finally:
        if probe is not None and probe.poll() is None:
            probe.terminate()
            try:
                probe.wait(timeout=3)
            except subprocess.TimeoutExpired:
                probe.kill()
                probe.wait()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", nargs="?", choices=("codex", "claude"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="query now, ignoring the polling interval")
    mode.add_argument("--ingest", action="store_true", help="silently receive Claude statusLine JSON from stdin")
    mode.add_argument("--watch", action="store_true", help="continuously publish both quota widgets")
    args = parser.parse_args()
    if args.watch and args.provider is not None:
        parser.error("--watch publishes both providers; do not specify one")
    if not args.watch and args.provider is None:
        parser.error("a provider is required")
    if args.ingest and args.provider != "claude":
        parser.error("--ingest is only available for Claude")
    os.umask(0o077)
    if args.watch:
        CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        watch()
        return
    path = CACHE_DIR / f"{args.provider}.json"
    if args.ingest:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            ingest_native(path, json.load(sys.stdin))
        except (OSError, ValueError):
            pass  # Missing/malformed native data must not interfere with Claude's UI.
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache = read_cache(path)
    # tmux can show this line immediately while a query is in flight.
    print(render(args.provider, cache, time.time()), flush=True)
    if args.refresh or should_refresh(args.provider, cache, time.time()):
        cache, failure = refresh(args.provider, path, args.refresh)
        print(render(args.provider, cache, time.time()), flush=True)
        if failure:
            sys.exit(f"{args.provider} query failed: {failure}")


if __name__ == "__main__":
    main()
