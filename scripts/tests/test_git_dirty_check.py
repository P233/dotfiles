import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "git-dirty-check.py"
spec = importlib.util.spec_from_file_location("dirty_check", SCRIPT)
dirty = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dirty)


class GitDirtyCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.environment = {**os.environ, "HOME": str(self.home),
                            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        self.patch = patch.dict(os.environ, self.environment)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def git(self, repo, *args):
        return subprocess.check_output(["git", "-C", str(repo), *args],
                                       stderr=subprocess.DEVNULL, text=True)

    def repo(self, name="example"):
        repo = self.home / "Projects" / name
        repo.mkdir(parents=True)
        self.git(repo, "init", "-b", "main")
        self.git(repo, "config", "user.name", "Fixture")
        self.git(repo, "config", "user.email", "fixture@example.invalid")
        (repo / "file.txt").write_text("initial\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "initial")
        return repo

    def test_clean_and_unborn_repositories_are_clean(self):
        self.repo()
        config = self.home / ".config"
        config.mkdir()
        self.git(config, "init")
        self.assertEqual(dirty.scan(self.home), [])

    def test_scan_does_not_rewrite_the_index_of_a_clean_repository(self):
        repo = self.repo()
        tracked = repo / "file.txt"
        # A changed timestamp makes an ordinary `git status` refresh and rewrite the index.
        os.utime(tracked, (tracked.stat().st_atime, tracked.stat().st_mtime + 60))
        index = repo / ".git/index"
        before = index.read_bytes()
        self.assertEqual(dirty.scan(self.home), [])
        self.assertEqual(index.read_bytes(), before)

    def test_counts_staged_modified_untracked_and_rename_paths(self):
        repo = self.repo()
        self.git(repo, "mv", "file.txt", 'new "name".txt')
        (repo / 'new "name".txt').write_text("modified\n")
        (repo / "untracked\nname").touch()
        result = dirty.scan(self.home)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["subtitle"], "1 staged, 1 modified, 1 untracked")

    def test_dirty_worktree_with_git_file_is_discovered(self):
        repo = self.repo()
        worktree = self.home / "Projects/group/worktree"
        worktree.parent.mkdir()
        self.git(repo, "worktree", "add", "-b", "feature", str(worktree))
        self.assertTrue((worktree / ".git").is_file())
        (worktree / "file.txt").write_text("worktree edit\n")
        self.assertEqual(dirty.scan(self.home)[0]["arg"], str(worktree))

    def test_scan_preserves_the_original_depth_limit(self):
        repo = self.repo("group/too/deep")
        (repo / "file.txt").write_text("edit\n")
        self.assertEqual(dirty.scan(self.home), [])

    def tracked_repo_with_unpushed_commit(self):
        repo = self.repo()
        remote = self.home / "remote.git"
        remote.mkdir()
        self.git(remote, "init", "--bare")
        self.git(repo, "remote", "add", "origin", str(remote))
        self.git(repo, "push", "-u", "origin", "main")
        self.git(repo, "commit", "--allow-empty", "-m", "unpushed")
        return repo

    def test_unpushed_commits_are_reported(self):
        self.tracked_repo_with_unpushed_commit()
        self.assertEqual(dirty.scan(self.home)[0]["subtitle"], "1 unpushed commit")

    def test_a_missing_upstream_branch_is_reported_instead_of_all_clean(self):
        repo = self.tracked_repo_with_unpushed_commit()
        self.git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(dirty.scan(self.home)[0]["subtitle"], "upstream origin/main is missing")

    def test_broken_git_marker_is_reported_instead_of_all_clean(self):
        repo = self.home / "Projects/broken"
        repo.mkdir(parents=True)
        (repo / ".git").write_text("gitdir: /missing-fixture-repo\n")
        self.assertIn("Git status failed", dirty.scan(self.home)[0]["subtitle"])

    def test_an_unborn_branch_with_an_upstream_has_nothing_to_push(self):
        repo = self.home / "Projects/unborn"
        repo.mkdir(parents=True)
        self.git(repo, "init", "-b", "main")
        self.git(repo, "remote", "add", "origin", str(self.home / "remote.git"))
        self.git(repo, "config", "branch.main.remote", "origin")
        self.git(repo, "config", "branch.main.merge", "refs/heads/main")
        self.assertEqual(dirty.scan(self.home), [])

    def test_conflicts_have_an_explicit_count(self):
        repo = self.repo()
        self.git(repo, "checkout", "-b", "other")
        (repo / "file.txt").write_text("other\n")
        self.git(repo, "commit", "-am", "other")
        self.git(repo, "checkout", "main")
        (repo / "file.txt").write_text("main\n")
        self.git(repo, "commit", "-am", "main")
        subprocess.run(["git", "-C", str(repo), "merge", "other"], capture_output=True)
        (repo / "other").touch()
        self.assertEqual(dirty.scan(self.home)[0]["subtitle"], "1 untracked, 1 conflicted")

    def test_cli_encodes_quotes_and_newlines_in_repository_names(self):
        repo = self.repo('quoted"\nrepository')
        (repo / "file.txt").write_text("edit\n")
        result = subprocess.check_output(["/usr/bin/python3", "-B", str(SCRIPT)],
                                         env=self.environment, text=True)
        self.assertEqual(json.loads(result)["items"][0]["arg"], str(repo))
        self.assertEqual(len(result.splitlines()), 1)

    def test_timeout_is_visible(self):
        repo = self.repo()
        with patch.object(dirty, "git", side_effect=subprocess.TimeoutExpired("git", 15)):
            self.assertIn("TimeoutExpired", dirty.check_repo(repo, self.home)["subtitle"])


if __name__ == "__main__":
    unittest.main()
