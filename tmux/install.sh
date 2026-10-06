#!/bin/sh
set -eu

if [ ! -f "$HOME/.config/tmux/tmux.conf" ]; then
    echo 'Clone this repository at ~/.config before installing tmux.' >&2
    exit 1
fi


# Keep the external OpenRig block and any other existing settings intact.
/usr/bin/python3 - <<'PY'
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

PY

echo 'tmux configured. Reload with: tmux source-file ~/.tmux.conf'
