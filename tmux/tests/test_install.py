import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


class TmuxInstallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tmux install ")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        source = self.home / ".config/tmux/tmux.conf"
        source.parent.mkdir(parents=True)
        source.write_text("# fixture tmux config\n")
        self.source = source
        binary = self.home / ".local/bin/codexbar"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.environment = {**os.environ, "HOME": str(self.home),
                            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}
        self.environment.pop("CLAUDE_CONFIG_DIR", None)

    def install(self, check=True):
        return subprocess.run(["sh", str(INSTALLER)], env=self.environment,
                              check=check, capture_output=True, text=True)

    def test_fresh_install_writes_one_private_source_line(self):
        self.install()
        config = self.home / ".tmux.conf"
        self.assertEqual(config.read_text(), "source-file ~/.config/tmux/tmux.conf\n")
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.install()
        self.assertEqual(config.read_text().count("source-file"), 1)

    def test_reload_setup_preserves_existing_openrig_config_and_file_mode(self):
        config = self.home / ".tmux.conf"
        config.write_text("# OpenRig managed block\nset -g history-limit 50000\n")
        config.chmod(0o640)
        self.install()
        self.assertTrue(config.read_text().startswith("# OpenRig managed block\nset -g history-limit 50000\n"))
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        first = config.read_bytes()
        self.install()
        self.assertEqual(config.read_bytes(), first)

    def test_a_root_config_symlink_is_preserved_without_self_sourcing(self):
        config = self.home / ".tmux.conf"
        config.symlink_to(self.source)
        self.install()
        self.assertTrue(config.is_symlink())
        self.assertEqual(self.source.read_text(), "# fixture tmux config\n")


    def test_missing_repository_is_rejected_before_installing_dependencies(self):
        self.source.unlink()
        (self.home / ".local/bin/codexbar").unlink()
        curl = self.bin / "curl"
        curl.write_text('#!/bin/sh\ntouch "$HOME/downloaded"\n')
        curl.chmod(0o755)
        result = self.install(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "downloaded").exists())
