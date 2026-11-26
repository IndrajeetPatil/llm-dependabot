#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# dependencies = ["pyyaml>=6.0.4"]
# ///
"""Fail if a staged file or commit message names a repository from private.yaml.

prek passes staged file paths at the pre-commit stage and the commit message
file at the commit-msg stage; both are checked the same way. Without a local
private.yaml there is nothing to protect, so the check passes.
"""

import re
import sys
from pathlib import Path

import yaml

PRIVATE_FILE = Path(__file__).resolve().parent.parent / "private.yaml"


def main(paths: list[str]) -> int:
    """Return 1 if any of the files names a private repository, else 0."""
    if not PRIVATE_FILE.exists():
        return 0
    names = (yaml.safe_load(PRIVATE_FILE.read_text(encoding="utf-8")) or {}).get(
        "repos",
    ) or []
    if not names:
        return 0
    alternation = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    pattern = re.compile(rf"(?<![\w.-])(?:{alternation})(?![\w-])", re.IGNORECASE)
    failed = False
    for raw in paths:
        path = Path(raw)
        if path.resolve() == PRIVATE_FILE:
            print(f"{raw}: private.yaml must never be committed")
            failed = True
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError, FileNotFoundError:
            continue
        for number, line in enumerate(lines, start=1):
            if line.startswith("#") and path.name == "COMMIT_EDITMSG":
                continue  # git's commented-out template lines
            if match := pattern.search(line):
                print(f"{raw}:{number}: names private repository {match[0]!r}")
                failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
