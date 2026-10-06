#!/bin/sh
set -eu

if [ ! -f "$HOME/.config/tmux/tmux.conf" ]; then
    echo 'Clone this repository at ~/.config before installing tmux.' >&2
    exit 1
fi

# Install only a missing CLI; upgrading means changing this pinned release and its checksums.
codexbar_version=0.72.0
if [ ! -x "$HOME/.local/bin/codexbar" ]; then
    case "$(uname -s):$(uname -m)" in
        Darwin:arm64)
            arch=arm64
            sha256=64d627747ad8c58c40ea2d1f1c30eafd2bdbcc9d50b0a81cf77bb5e5c21bc449 ;;
        Darwin:x86_64)
            arch=x86_64
            sha256=97e432e1cf37d92b07d2e176a12032c100c54da36de97db9eada2865d0aae84b ;;
        *) echo 'CodexBar CLI requires macOS.' >&2; exit 1 ;;
    esac
    archive=$(mktemp)
    trap 'rm -f "$archive"' EXIT HUP INT TERM
    curl --fail --location --connect-timeout 15 --max-time 120 \
        "https://github.com/steipete/CodexBar/releases/download/v$codexbar_version/CodexBarCLI-v$codexbar_version-macos-$arch.tar.gz" \
        -o "$archive"
    printf '%s  %s\n' "$sha256" "$archive" | shasum -a 256 --check
    directory="$HOME/.local/share/codexbar/v$codexbar_version"
    mkdir -p "$directory" "$HOME/.local/bin"
    tar -xzf "$archive" -C "$directory"
    test -x "$directory/CodexBarCLI"
    ln -sf "$directory/CodexBarCLI" "$HOME/.local/bin/codexbar"
fi

# Keep the external OpenRig block and any other existing settings intact.
/usr/bin/python3 - <<'PY'
import json
import os
from pathlib import Path
import tempfile


def replace_file(path, text):
    """Atomically write text, keeping an existing file's mode or creating it private."""
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
            handle.flush()
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


source = Path.home() / ".config/tmux/tmux.conf"
config = (Path.home() / ".tmux.conf").resolve()
if config != source.resolve():
    line = "source-file ~/.config/tmux/tmux.conf"
    text = config.read_text() if config.exists() else ""
    if line not in text.splitlines():
        replace_file(config, text.rstrip("\n") + ("\n\n" if text else "") + line + "\n")

# Claude's status line receives native usage without another API request.
# Keep an existing custom status line intact.
directory = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
settings = (directory / "settings.json").resolve()
original = settings.read_bytes() if settings.exists() else None
data = json.loads(original) if original is not None else {}
if not isinstance(data, dict):
    raise ValueError("Claude settings must be a JSON object")
command = '/usr/bin/python3 "$HOME/.config/tmux/scripts/usage.py" claude --ingest'
status_line = data.get("statusLine")
if not status_line:
    if original is not None:
        backup = directory / "settings.json.before-tmux-usage"
        try:
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # Keep one original restore point instead of accumulating backups.
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(original)
    data["statusLine"] = {"type": "command", "command": command}
    replace_file(settings, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print("Claude native usage collector configured.")
elif not isinstance(status_line, dict) or status_line.get("command") != command:
    print("Existing Claude status line retained; see tmux/README.md for native usage setup.")
PY

echo 'tmux dependencies installed. Reload with: tmux source-file ~/.tmux.conf'
