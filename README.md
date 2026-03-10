# ~/.config

Personal dotfiles managed with git.

## Setup

Prerequisites: Xcode CLI tools, Node.js, VSCode with `code` CLI.

```sh
git clone <repo> ~/.config
make install    # symlink VSCode configs, install open-in-emacs extension, compile toggle-app
```

To remove the toggle-app binary:

```sh
make clean
```

## Fish Shell

Plugins are managed by [fisher](https://github.com/jorgebucaran/fisher).
To restore plugins on a new machine:

```fish
fisher update
```

### File conventions

| Path | Tracked | Notes |
|------|---------|-------|
| `fish/config.fish` | yes | Main config |
| `fish/fish_plugins` | yes | Fisher plugin list |
| `fish/fish_variables` | no | Runtime state, machine-specific |
| `fish/functions/u_*.fish` | yes | **Hand-written functions (use `u_` prefix)** |
| `fish/functions/*` (others) | no | Plugin-generated |
| `fish/completions/` | no | Plugin-generated |
| `fish/conf.d/` | no | Plugin-generated |

**Rule:** all hand-written fish functions must be named `u_<name>.fish`.
This prefix is automatically tracked by `.gitignore`.

## Git

Config is at `git/config` (XDG path, replaces `~/.gitconfig`).
Git reads this location natively since version 1.7.12 — no extra setup needed.

## Karabiner-Elements

Config at `karabiner/karabiner.json`. Includes Dvorak layout remapping for the
built-in keyboard and an F13 shortcut to toggle Ghostty (via LL Dongle).

### toggle-app

`toggle-app <AppName>` — fast app toggle via NSWorkspace API (~10ms):

- App is frontmost → hide it
- App is running but not frontmost → activate it
- App is not running → launch it

No Accessibility permissions required.

## Ghostty

Config at `ghostty/config`.

## VSCode

Config files are symlinked from `vscode/` into `~/Library/Application Support/Code/User/`.

| File | Purpose |
|------|---------|
| `vscode/settings.json` | Editor settings |
| `vscode/keybindings.json` | Custom keybindings |
| `vscode/open-in-emacs/` | Custom extension: open current file in Emacs |

`Ctrl+F12` opens the current file in Emacs at the current line via `emacsclient`.
If Emacs is not running, it launches Emacs.app automatically.

## Emacs

A minimal config derived from [P233/emacs.d](https://github.com/P233/emacs.d),
trimmed down for code reading and git (Magit) use only. Emacs server is started
automatically on launch to support `emacsclient` connections from VSCode.

Packages are managed by [straight.el](https://github.com/radian-software/straight.el).
To restore on a new machine, just open Emacs — straight.el will bootstrap itself and install all packages automatically.

### File conventions

| Path | Tracked | Notes |
|------|---------|-------|
| `emacs/early-init.el` | yes | Startup optimizations |
| `emacs/init.el` | yes | Bootstrap + core settings |
| `emacs/lisp/*.el` | yes | Hand-written modules |
| `emacs/straight/` | no | Packages installed by straight.el |
| `emacs/var/` | no | Runtime data (no-littering) |
| `emacs/etc/` | no | Generated config (no-littering) |
| `emacs/server/` | no | Server socket for emacsclient |
