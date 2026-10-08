#!/bin/sh
set -eu

usage_script="$HOME/.config/tmux/scripts/usage.py"
/usr/bin/python3 "$usage_script" codex --refresh >/dev/null &
codex_query=$!
# One failed process must not skip the other result.
status=0
/usr/bin/python3 "$usage_script" claude --refresh >/dev/null || status=1
wait "$codex_query" || status=1

# Attached quota watchers publish changed caches within one second. A forced
# refresh-client -S would kill and restart every status job, including probes.
exit "$status"
