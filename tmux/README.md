# tmux

`~/.tmux.conf` retains existing local settings and sources this directory's
`tmux.conf`; no tmux plugins are required. Restore this setup with
`make install-tmux` from the repository root. The installer preserves existing
root settings, installs only missing dependencies and verifies the pinned
CodexBar CLI archive checksum. It also configures the silent Claude
native usage collector when no custom Claude status line is present. It does not
restart or reload a live server.

One status row sits at the top on a slightly lighter Dracula background
(`#343746`), without Powerline separators or battery information. The clickable
window list (tabs) sits on the left; CPU, RAM and quota bars sit on the right,
followed by the focus timer at the far right.
Each tab shows `[number:name]`, with a name that normally follows its running
command. Both active and inactive tabs keep their brackets; purple text and a
selection background highlight the current tab without changing its width. The
session name is hidden. CPU and RAM are hidden below 150 columns to leave room
for tabs, quotas and the timer. Tabs, status widgets, labels and bars use one-space
separators; blank cells inside a quota bar represent its fixed-width unfilled
area. CPU and RAM are separated by ` · `. The clock is hidden.
Closing a tab renumbers the remaining tabs from 1, so Cmd+1 through Cmd+8 follow
their visible order.

Codex uses light blue (`#a6c8ff`); Claude uses light orange (`#ffb890`).
Twelve-cell bars mean **remaining quota**, so a longer colored fill means more
quota available. Percentages sit inside each bar at the left, with one cell of
padding. Text is regular dark (`#282a36`) on the brand-colored fill and white
on the dark unfilled track (`#21222c`). A terminal cannot specify half-cell padding, reduce
just the percentage font size, or change the text row's pixel
height. Codex shows one bar, preferring 5h when present and falling back to 7d.
Claude's two bars appear inline, 5h then 7d, separated by spaces without duration
labels. The percentage is left-aligned; the reset countdown is right-aligned
inside the same bar, with one cell of padding at each outer edge. Both fields
use the same contrasting text colors. The entire twelve-cell width determines
the colored fill and stays fixed when countdown units change. Countdowns contain plain time text,
such as `35m`, `2h` or `3d`, without an icon.
PragmataPro Mono Liga supplies the native one-cell Nerd refresh/reset glyph
`U+F021`, verified against the installed
font and the [designer's symbol list](https://github.com/fabrizioschiavi/pragmatapro-semiotics/blob/main/Symbols.csv).
System metrics and agents use the plain ASCII separator ` | `; Claude's two bars
use one space. Countdowns derive from the cached deadline without fetching again,
using one unit, with minutes rounded up and hours/days shown without smaller units.
Both values reuse the same sanitized quota cache and refresh lock.

Click anywhere in the Codex section (including its credit balance) to open
<https://chatgpt.com/settings/usage?tab=overview> in the default browser.
Click anywhere in the Claude section, including either bar, to open
<https://claude.ai/new#settings/usage>. Native tmux control ranges 1, 2 and 3
are reserved for Codex, Claude and the timer; the `|` separators have no click action.

`scripts/cpu.sh` reports the summed process CPU share divided by logical cores.
`scripts/ram.sh` reports used physical RAM as total minus free pages and reclaimable
file-backed (including speculative) and purgeable pages. This is close to
Activity Monitor's Memory Used percentage; sampling times can differ. It is not
the separate memory-pressure metric.

Status producers stay running while their client is attached. CPU and RAM each
sample every five seconds; the timer publishes every second. One quota producer
checks the existing local caches every second and publishes only when the rendered
text changes. Codex queries run in a separate child at most once per 180 seconds;
Claude native updates therefore remain visible during a slow Codex query.
Repainting the row or restarting the timer does not restart the data collectors.
tmux still draws one status row, rather than independent graphical widgets.
Each client owns its producers, while the existing query locks deduplicate remote
requests across clients. Detaching stops that client's producers and active probe.
A probe cancelled by stopping its producer (detach, layout change or session
switch) does not count as an attempt, so the replacement producer queries without
waiting for the 180-second interval.
The quota producer also checks its parent on each tick, so a crashed or forcibly
killed tmux server cannot leave it querying in the background.
This trades a small resident process footprint for fewer interpreter startups.

tmux hooks stop obsolete producers when `status`, `status-right` or `status-format`
changes. Session-local changes affect only clients in that session. Resizing below
150 columns stops that client's CPU/RAM producers; widening starts them again.
Switching sessions replaces only that client's producers to match the new layout.
An unchanged configuration reload preserves the running producers. The cleanup
helper runs only for layout changes, client attachment/session switches and resize
events; it is not another resident process or a periodic tmux query. It identifies
jobs from tmux's job list using their exact script commands and client metadata,
without scanning or signalling
pane processes. Normal updates and the manual quota refresh do not force
`refresh-client -S`.

## Focus timer

The timer starts automatically with **52 minutes of Focus**, followed by
**17 minutes of Break**, repeating indefinitely. Focus is green (`#50fa7b`);
Break is gray (`#b0b0bd`). The remaining `MM:SS` appears inside the twelve-cell
bar, left-aligned with one cell of padding. Digits use dark text (`#282a36`)
over the bright fill and white over the unfilled track, changing color at the
fill boundary without moving. Its fill shows remaining time and shrinks as the
phase ends. It publishes the remaining time once per second.

During the last 60 seconds of Focus, its label and remaining time turn yellow
(`#f1fa8c`). A status update with 55–60 seconds remaining shows a centered native macOS
overlay saying **1 minute remaining**. It disappears after five seconds, has no
buttons, lets clicks pass through, and does not take keyboard focus. The AppKit
helper runs in the background without blocking tmux or requiring extra packages.
Break remains gray and does not show a reminder. tmux keeps one shared reminder
attempt marker per server, so concurrent clients and configuration reloads do not
repeat it; restarting the timer begins a new reminder cycle. Reminders require
an attached status bar. Late updates after detaching or waking do not replay the
reminder, and the native helper checks the deadline again before showing it.

A failed reminder shows a short tmux status message without entering view mode.
The latest error, including the underlying command's stderr, is saved to
`~/.cache/tmux-focus/reminder-error.log` (or under `$XDG_CACHE_HOME`), limited to
4 KiB with private permissions. This diagnostic file is overwritten on the next
failure; it does not control timing or retries. A failed attempt is not repeated
within the same Focus cycle. If tmux is unavailable, the error log remains the
diagnostic source.

There is one command, which immediately starts a fresh 52-minute focus phase:

```sh
tmux focus-restart
```

From the tmux command prompt (Ctrl+B, then `:`), enter `focus-restart`.
Click the timer label or bar for the same restart.
All sessions on the same tmux server share one `@focus-started-at` timestamp.
Reloading the configuration and detaching preserve it; elapsed wall time,
including sleep, determines the current phase after reattaching. A new tmux
server starts a new focus cycle. Each attached client has a tmux-managed timer
producer that exits on detach; there is no separate daemon or timer state file.
Command-alias index 100 is reserved for this command.

## Ghostty and panes

Ghostty starts `tmux new-session -A -s main`, creating or reattaching the persistent
`main` session. All Ghostty windows share that session. Closing a Ghostty window
detaches its client; tmux keeps the session and its programs running.

Ghostty's macOS pane and tab shortcuts now control tmux. See the
[shortcut list](shortcuts.md) for Command-key mappings, the unchanged Ctrl+B
fallbacks, and native Ghostty controls. New panes and tabs inherit the active
pane's working directory. Cmd+9 selects the last tab, matching Ghostty's default;
Ctrl+B followed by `9` still selects the tab numbered 9.

Ghostty sends dedicated CSI sequences (`9001~` through `9019~` and `9021~`
through `9029~`). tmux maps these to `User100` through `User128`, reserving
these indexes for this integration. Root-table bindings consume the keys before
the foreground program receives them. No helper process or plugin is required.
These keys always control the outer tmux, including when a pane runs SSH or a
nested tmux. The default prefix and ordinary Shift+Enter remain unchanged.

Mouse support and `focus-follows-mouse` let hovering over a pane activate it.
Pane borders use the native `simple` ASCII style: `|` vertically, `-` horizontally,
and `+` at intersections. Adjacent panes share one separator, with no extra pane
title row. Native arrow markers point into the active pane, avoiding the default
half-colored border when there are exactly two panes. The active border and its
arrows use bright Dracula purple (`#bd93f9`) on the terminal's default background so they
stand out from inactive borders. Ghostty's four-codepoint font mapping displays
these native arrows as solid triangles; restore it with `make install-ghostty`.
The generated font uses geometric outlines and PragmataPro-compatible cell
metrics, without modifying the installed PragmataPro fonts. The mapping applies
to the same arrow characters elsewhere in Ghostty too. Native arrows have fixed
positions near the start of each adjoining border; tmux cannot configure a
marker at both ends.
Native tmux supports no dashed border style.
Cmd+W confirms closing the active tmux pane; Cmd+Option+W confirms closing the
current tmux tab and all its panes. Confirm with `y` or cancel with `n`/Escape.
Both commands capture their target when the prompt opens. Closing a pane
terminates its program. Closing the final pane closes its tab; closing the final
tab ends the session and the terminal surface can close. F13 hides Ghostty,
and Ctrl+B followed by `d` detaches without terminating the session's programs.
Ctrl+W and Ctrl+D are passed to the foreground program; Ctrl+D may exit a shell
or an agent and is not a pane-close shortcut.

Cmd+N and native window-close shortcuts are disabled. This supports a single
Ghostty-window workflow, but is not a strict window-count limit: the app menu
and dropping files onto the Dock icon can still create native windows. All
new Ghostty windows attach to the same `main` session.

Extended keys use CSI-u encoding, with Ghostty marked as supporting `extkeys`.
This preserves Shift+Enter for programs that request extended key reporting.
Existing terminal clients must reattach to pick up the terminal feature change.
Programs already running may also need to be resumed after a restart to
negotiate the keyboard protocol again.

Reload Ghostty with Cmd+Shift+, for the new keybindings. The startup command takes
effect for newly created terminal surfaces.

## Usage data

CodexBar CLI 0.72.0 for macOS arm64 is installed at `~/.local/bin/codexbar`, linked
to `~/.local/share/codexbar/v0.72.0/CodexBarCLI`. Its release archive was verified
against the GitHub release SHA256. The menu bar app is not required.

Codex uses CodexBar's explicit OAuth source and is queried at most once every
180 seconds, including while a window is used up. Claude makes **no automatic
query**: its native `statusLine` command passes `rate_limits.five_hour` and
`rate_limits.seven_day` to `usage.py claude --ingest`. The collector reads JSON
from stdin, saves only quota fields and prints nothing, so it adds no status row
inside Claude. Data arrives after Claude's API responses; typing or repainting
can repeat already-known values, and each session reports its own last response,
so snapshots from several sessions arrive out of order. Each window keeps the
newer measurement: a later reset deadline starts a new period, and within one
period usage only grows, so a snapshot with more remaining quota is older and is
ignored. Deadlines within an hour count as one period, because manual results
read rounded reset times from the CLI; without a deadline, arrival order
decides. Repeated snapshots therefore change nothing, and a manual result is
replaced only by newer native data. This is subscription quota, separate from
API billing.
See the [official status-line data contract](https://code.claude.com/docs/en/statusline).

`make install-tmux` adds this command to `~/.claude/settings.json` (or
`$CLAUDE_CONFIG_DIR/settings.json`), preserves all other settings and keeps one
private original backup at `settings.json.before-tmux-usage`. Re-running it is
idempotent. It preserves a different existing custom status line: in that case,
integrate the collector into that command yourself rather than replacing it.
The command is:

```sh
/usr/bin/python3 "$HOME/.config/tmux/scripts/usage.py" claude --ingest
```

Claude Code must supply the native fields: they are available for Pro/Max after
the first API response in a trusted workspace. If an existing Claude session does
not pick up the settings change, restart/resume that session when convenient.
Idle sessions and usage on other devices may leave the last received snapshot
unchanged; use manual refresh to check independently. A window that a native
snapshot omits or that loses to a newer cached value keeps its value and its own
measurement time, so its `~` marker stays accurate.

A manual refresh queries Claude through CodexBar's native CLI `/usage` probe,
reusing the existing sign-in in a temporary directory without submitting a
coding task or scraping browser cookies.

A Codex query also returns the remaining credit balance (extra usage beyond the
plan's rate limits). It appears after the Codex bar in compact form, such as
`850`, `62.1k` or `1.2M`, and is hidden when the balance is zero, unavailable or
expired with the bar's measurement. Codex keeps polling while a window is used
up, so the balance stays current while credits are being spent.

Queries have a 25-second timeout that also terminates probe child processes.
Only sanitized windows, timestamps, the Codex credit balance and the last
failure's exception name are stored in
`~/.cache/tmux-usage/` (or `$XDG_CACHE_HOME/tmux-usage/`). Each provider has a
query lock and a separate short cache-write lock. A native callback can therefore
publish during a query; each queried window is merged by its measurement time,
preserving newer native values while updating older windows from the same query.
There is no persistent updater daemon. With no attached status bar, automatic
queries wait until a client attaches; with an active bar, eligibility is checked
every second without running a new CLI process until a query is due.

- `0%` with a countdown: the window is used up until that reset.
- `` (`U+F021`) instead of a percentage, with countdown `0m`: the cached reset deadline has
  passed and a fresh quota window is pending. Codex keeps a known 5h window in
  this state instead of switching to its weekly quota. Claude stays in this
  state until its next native update or a manual refresh.
- `—` instead of a percentage: the window is unavailable or the measurement is
  expired. Codex measurements expire after 15 minutes. Claude retains its last
  received snapshot during idle periods. This is distinct from a 0% bar.
  A countdown of `—` means the reset time is unavailable.
- `~`: retained data after a failed fetch, or a window last measured more than
  5 minutes ago. It is the last known
  quota, not a guarantee of current usage on other devices. Passing a reset
  deadline never assumes that quota is now 100%.
- Claude keeps a missing five-hour measurement as `—` in the first position;
  its weekly percentage stays in the second position.

Press **Ctrl+B, then Ctrl+R** to refresh both Codex and Claude in the background.
You can hold Ctrl and press B followed by R. Ctrl+R without the tmux prefix
continues to reach the foreground program. Manual refresh bypasses the Codex
polling interval and is the only way Claude is queried independently, allowing
an early reset to be detected; provider query locks still prevent duplicate
requests. A failed query exits with status 1 and names the provider and
exception, which Ctrl+B Ctrl+R shows in tmux view mode.
Attached quota producers show changed caches within one second, without a forced
status refresh that would restart the other jobs.

Refresh a provider from a shell:

```sh
python3 ~/.config/tmux/scripts/usage.py codex --refresh
python3 ~/.config/tmux/scripts/usage.py claude --refresh
```

## Reload

```sh
tmux source-file ~/.tmux.conf
```

The status row calls this repository's scripts directly. Ghostty's feature entry
uses array index 100 so reloading cannot append duplicates.
Status lifecycle hooks reserve index 150. Their `@status-jobs-layout` snapshot
contains the effective layouts of current sessions; it does not own timer or
quota state. Layout edits automatically clean up old jobs.

After editing producer **script contents**, restart the attached status producers
to load the new code (the timer's start timestamp and quota caches are preserved):

```sh
~/.config/tmux/scripts/status-jobs.py --layout
```

Check the tmux scripts with the interpreter they run under:

```sh
/usr/bin/python3 -B -m unittest discover -s ~/.config/tmux/tests -v
```
