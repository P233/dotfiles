# tmux

`~/.tmux.conf` retains the existing OpenRig block and sources this directory's
`tmux.conf`; no tmux plugins are required. Restore this setup with
`make install-tmux` from the repository root. The installer preserves existing
root settings. It does not restart or reload a live server.

One status row sits at the top on a slightly lighter Dracula background
(`#343746`), without Powerline separators. The clickable window list (tabs) sits
on the left. Each tab shows `[number:name]`, with a name that normally follows
its running command. Purple text and a selection background highlight the
current tab without changing its width. The session name and clock are hidden.

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

## Reload

```sh
tmux source-file ~/.tmux.conf
```

Ghostty's feature entry uses array index 100 so reloading cannot append duplicates.

Check the tmux scripts with the interpreter they run under:

```sh
/usr/bin/python3 -B -m unittest discover -s ~/.config/tmux/tests -v
```
