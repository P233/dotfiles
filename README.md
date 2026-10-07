# ~/.config

Personal dotfiles managed with git.

## Setup

Prerequisites: macOS, Xcode CLI tools, Git, Node.js, Fish, uv and tmux 3.7+.
For the configured Fish plugins, also install the [CLI dependencies below](#fish-shell).
Ghostty uses the separately installed
PragmataPro Mono Liga font; its licensed font files are not in this repository.

```sh
git clone <repo> ~/.config
cd ~/.config
make install    # restore scripts, pnpm, Ghostty fonts and tmux; apply macOS defaults
```

Individual targets allow restoring one tool at a time:

| Target | Effect |
| --- | --- |
| `make install-scripts` | Install or update Git check and SSH signing adapter |
| `make install-pnpm` | Restore pnpm and pnpx in a stable user directory without Corepack |
| `make install-ghostty` | Generate/install the four-symbol font for solid tmux arrow indicators |
| `make install-tmux` | Install a missing CodexBar CLI; configure native Claude usage; preserve existing settings |
| `make install-macos` | Apply the recorded preferences and restart Dock |
| `make check` | Run focused script and configuration checks |

`make install` already runs `make install-scripts`; no separate script-install
step is needed after a full installation. The script target copies
`scripts/git-dirty-check.py` and `scripts/agent-ssh-sign.sh` into `~/.local/bin`
as `git-dirty-check` and `agent-ssh-sign`. These are installed copies, so pulling
or editing their source files does not update the installed commands.
After either script changes, refresh just those commands with:

```sh
cd ~/.config
make install-scripts
```

The pnpm version is pinned in `Makefile`. pnpm respects
project package-manager versions through its native version switching. CLI
downloads and generated packages live outside the configuration source.

To remove the Git check binary (the signing adapter is retained):

```sh
make clean
```

## Fish Shell

The configured [fzf.fish](https://github.com/PatrickF1/fzf.fish#installation)
plugin needs `fzf` for searching, `fd` for listing files and `bat` for file
previews. Install these CLI dependencies separately; neither `make install`
nor Fisher installs them:

```sh
brew install fzf fd bat
```

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
| `fish/functions/p.fish` | yes | Hand-written pnpm shorthand |
| `fish/functions/*` (others) | no | Plugin-generated |
| `fish/completions/` | no | Plugin-generated |
| `fish/conf.d/` | no | Plugin-generated |

Add each hand-written function explicitly to the `.gitignore` allowlist.
PATH entries use `fish_add_path --path`; sourcing the config repeatedly does
not append duplicate paths or persist new universal variables. `~/.local/bin`
contains the pnpm and CodexBar CLI entry points; `~/Library/pnpm` contains the
existing global ACP commands.

## Git

Config is at `git/config` (XDG path, replaces `~/.gitconfig`).
Git reads this location natively since version 1.7.12 — no extra setup needed.

SSH commit signing uses `scripts/agent-ssh-sign.sh`, installed as
`~/.local/bin/agent-ssh-sign`. It connects to the existing agent socket at
`~/.local/state/agent-signing/agent.sock`. The agent, private keys and
`~/.ssh/allowed_signers` are provisioned separately. The 1Password SSH agent
configuration selects the `Agent SSH` vault; this does not create a signing agent.

`git-dirty-check` scans `~/Projects` and this configuration directory for modified
files and unpushed commits. It supports worktrees, outputs Alfred Script Filter
JSON, and reports Git errors or a configured upstream whose branch is missing
instead of treating them as clean.

## macOS

`macos/defaults.sh` records the selected window and Dock preferences.
Run `make install-macos` to apply them and restart the Dock.
See the [animation inventory](macos/README.md) for the recorded local state,
independent controls, and macOS version limitations. Reduce Motion stays off.

## Karabiner-Elements

Config at `karabiner/karabiner.json`. Includes Dvorak layout remapping for the
built-in keyboard, where Cmd+F11 sends F13 for Ghostty's global show/hide shortcut.

## Ghostty

Config at `ghostty/config`. Ghostty creates or reattaches the persistent tmux
`main` session. The tmux configuration provides one top status row with tabs
and cached agent quota bars. See [tmux setup and shortcuts](tmux/README.md).
Ghostty's pane and tab shortcuts control tmux through dedicated key sequences.
The default Ctrl+B prefix remains available; see the
[shortcut list](tmux/shortcuts.md).

`make install-ghostty` creates `~/Library/Fonts/TmuxSolidTriangles.ttf` with
FontTools (the build dependency is pinned in `Makefile` and managed by uv).
The font contains four independently generated geometric triangles with
PragmataPro-compatible cell metrics; it contains no licensed PragmataPro outlines.
Ghostty maps only `U+2190` through `U+2193` to this font, so native tmux arrows
appear as `◀ ▲ ▶ ▼`. Every occurrence of these four codepoints in Ghostty uses
the same mapping; copied text retains its original arrow character. Other text
uses the original font. Reload the config and open a new terminal surface, or
quit/reopen Ghostty, to apply this font mapping; existing tmux sessions persist.

## Other active tools

- Docker's `docker agent` still owns `cagent/`; its machine identity is ignored.
  Alma, Hunk, 1Password CLI and uv also remain installed; their runtime state
  is not configuration source.

## Repository boundaries

Credentials, account databases, Fish plugin output, Hunk update state, Python
bytecode, Serena local state and `work/` experiments are ignored.
Keep experimental evidence and private machine state out
of configuration commits. This repository does not contain Emacs's configuration,
which is maintained separately at `~/.emacs.d`. VS Code settings and extensions
are also maintained outside this repository; its native settings are regular
local files rather than links into this repository.
