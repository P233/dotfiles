#!/usr/bin/python3
"""List dirty or unpushed repositories as Alfred Script Filter JSON."""

import json
import os
from pathlib import Path
import subprocess


def git(repo, *args):
    return subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                          capture_output=True, timeout=15)


def repository_state(output):
    """Read change counts and upstream tracking from `git status --porcelain=v2 --branch -z`."""
    staged = modified = untracked = conflicts = 0
    upstream = ahead = None
    records = iter(output.split(b"\0"))
    for record in records:
        if record == b"# branch.oid (initial)":
            ahead = 0  # An unborn branch has no commits to push.
        elif record.startswith(b"# branch.upstream "):
            upstream = record.split(b" ", 2)[2].decode(errors="replace")
        elif record.startswith(b"# branch.ab "):
            # Git reports ahead/behind counts only while the upstream branch exists.
            ahead = int(record.split()[2])
        elif record.startswith(b"? "):
            untracked += 1
        elif record.startswith(b"u "):
            conflicts += 1
        elif record.startswith((b"1 ", b"2 ")):
            staged += record[2:3] != b"."
            modified += record[3:4] != b"."
            if record.startswith(b"2 "):
                # A rename or copy record is followed by its original path.
                next(records, None)
    changes = [(count, label) for count, label in
               ((staged, "staged"), (modified, "modified"),
                (untracked, "untracked"), (conflicts, "conflicted")) if count]
    return changes, upstream, ahead


def item(repo, home, subtitle):
    name = "~" + str(repo)[len(str(home)):]
    return {"title": name, "subtitle": subtitle, "arg": str(repo),
            "icon": {"path": "icon.png"}}


def check_repo(repo, home):
    try:
        status = git(repo, "status", "--porcelain=v2", "--branch", "-z")
        if status.returncode:
            reason = status.stderr.decode(errors="replace").strip()[:200]
            return item(repo, home, f"Git status failed: {reason}")
        changes, upstream, ahead = repository_state(status.stdout)
        problems = []
        if changes:
            problems.append(", ".join(f"{count} {label}" for count, label in changes))
        if upstream is not None and ahead is None:
            problems.append(f"upstream {upstream} is missing")
        elif ahead:
            problems.append(f"{ahead} unpushed commit" + ("s" if ahead != 1 else ""))
        return item(repo, home, " · ".join(problems)) if problems else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return item(repo, home, f"Git check failed: {type(error).__name__}")


def scan(home):
    items = []
    for root in (home / "Projects", home / ".config"):
        if not root.is_dir():
            continue

        def scan_error(error):
            items.append(item(Path(error.filename), home, f"Repository scan failed: {error.strerror}"))

        # Preserve the old find depth: the .git entry is at most three levels down.
        for directory, children, _files in os.walk(root, onerror=scan_error):
            repo = Path(directory)
            marker = repo / ".git"
            if marker.is_dir() or marker.is_file():
                result = check_repo(repo, home)
                if result:
                    items.append(result)
            children[:] = sorted(name for name in children if name != ".git")
            if len(repo.relative_to(root).parts) >= 2:
                children.clear()
    return items


def main():
    items = scan(Path.home())
    if not items:
        items = [{"title": "All clean ✓", "subtitle": "No dirty repos found", "valid": False}]
    print(json.dumps({"items": items}))


if __name__ == "__main__":
    main()
