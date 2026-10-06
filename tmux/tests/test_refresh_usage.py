import os
from pathlib import Path
import subprocess
import tempfile
import unittest


HELPER = Path(__file__).resolve().parents[1] / "scripts/refresh-usage.sh"


class ManualRefreshTests(unittest.TestCase):
    def test_provider_failure_still_waits_for_both_and_repaints(self):
        for failing in ("codex", "claude"):
            with self.subTest(failing=failing), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                scripts = home / ".config/tmux/scripts"
                scripts.mkdir(parents=True)
                (scripts / "usage.py").write_text(
                    "import os,sys,time\nfrom pathlib import Path\n"
                    "assert sys.argv[2:] == ['--refresh']\n"
                    "provider = sys.argv[1]\n"
                    "time.sleep(0.1 if provider == 'codex' else 0.02)\n"
                    "(Path.home() / (provider + '-finished')).touch()\n"
                    "sys.exit(1 if provider == os.environ['FAILED_PROVIDER'] else 0)\n")
                binaries = home / "bin"
                binaries.mkdir()
                tmux = binaries / "tmux"
                tmux.write_text(
                    '#!/bin/sh\nset -eu\n'
                    'test -f "$HOME/codex-finished"\n'
                    'test -f "$HOME/claude-finished"\n'
                    'printf "%s\\n" "$*" > "$HOME/repaint"\n')
                tmux.chmod(0o755)
                result = subprocess.run(
                    ["sh", str(HELPER)], capture_output=True, text=True, timeout=3,
                    env={**os.environ, "HOME": str(home), "FAILED_PROVIDER": failing,
                         "PATH": str(binaries) + os.pathsep + os.environ["PATH"]})
                self.assertNotEqual(result.returncode, 0, "provider failures must remain visible")
                self.assertTrue((home / "repaint").exists(), "a failure skipped the repaint")
                self.assertEqual((home / "repaint").read_text().strip(), "refresh-client -S")


if __name__ == "__main__":
    unittest.main()
