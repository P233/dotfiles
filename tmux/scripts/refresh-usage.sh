#!/bin/sh
set -eu

usage_script="$HOME/.config/tmux/scripts/usage.py"
/usr/bin/python3 "$usage_script" codex --refresh >/dev/null &
codex_query=$!
# One failed process must not skip the other result or the status redraw.
status=0
/usr/bin/python3 "$usage_script" claude --refresh >/dev/null || status=1
wait "$codex_query" || status=1

tmux refresh-client -S || status=1
exit "$status"
