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

    def test_bad_download_checksum_does_not_publish_a_binary_or_root_config(self):
        (self.home / ".local/bin/codexbar").unlink()
        uname = self.bin / "uname"
        uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Darwin;; -m) echo arm64;; esac\n')
        uname.chmod(0o755)
        curl = self.bin / "curl"
        curl.write_text('#!/bin/sh\nfor arg do target="$arg"; done\nprintf "invalid archive" > "$target"\n')
        curl.chmod(0o755)
        result = self.install(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / ".local/bin/codexbar").exists())
        self.assertFalse((self.home / ".tmux.conf").exists())

    def test_missing_repository_is_rejected_before_installing_dependencies(self):
        self.source.unlink()
        (self.home / ".local/bin/codexbar").unlink()
        curl = self.bin / "curl"
        curl.write_text('#!/bin/sh\ntouch "$HOME/downloaded"\n')
        curl.chmod(0o755)
        result = self.install(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "downloaded").exists())

    def test_native_collector_preserves_settings_and_creates_one_private_backup(self):
        path = self.home / ".claude/settings.json"
        path.parent.mkdir()
        original = json.dumps({"hooks": {"Stop": []}, "permissions": {"allow": ["fixture"]}})
        path.write_text(original)
        path.chmod(0o600)
        self.install()
        data = json.loads(path.read_text())
        self.assertEqual(data["hooks"], {"Stop": []})
        self.assertEqual(data["permissions"], {"allow": ["fixture"]})
        self.assertIn("claude --ingest", data["statusLine"]["command"])
        backup = path.with_name("settings.json.before-tmux-usage")
        self.assertEqual(backup.read_text(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        first = path.read_bytes()
        self.install()
        self.assertEqual(path.read_bytes(), first)
        self.assertEqual(backup.read_text(), original)

    def test_an_existing_custom_status_line_is_retained(self):
        path = self.home / ".claude/settings.json"
        path.parent.mkdir()
        original = json.dumps({"statusLine": {"type": "command", "command": "existing-command"}})
        path.write_text(original)
        result = self.install()
        self.assertEqual(path.read_text(), original)
        self.assertIn("Existing Claude status line retained", result.stdout)
        self.assertFalse(path.with_name("settings.json.before-tmux-usage").exists())

    def test_native_collector_respects_claude_config_directory(self):
        path = self.home / "custom claude/settings.json"
        self.environment["CLAUDE_CONFIG_DIR"] = str(path.parent)
        self.install()
        self.assertTrue(path.is_file())
        self.assertFalse((self.home / ".claude/settings.json").exists())
