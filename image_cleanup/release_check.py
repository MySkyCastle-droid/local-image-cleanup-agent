"""Fail closed on unsafe content in the publication directory."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ALLOWED_NAMES = {".gitignore", "LICENSE"}
ALLOWED_SUFFIXES = {".py", ".md", ".toml", ".ps1", ".txt", ".yml"}
FORBIDDEN_PARTS = {".venv", "node_modules", "artifact_work", "models", "output", "data", "work", "__pycache__"}
PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "windows_path": re.compile(r"[A-Za-z]:\\(?:Users|HOME)\\"),
    "private_key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "credential": re.compile(r"(?:gh[pousr]_|am_sk_|AKIA|sk-[A-Za-z0-9]{16})[A-Za-z0-9_-]{12,}"),
}


def _tracked(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z"],
        capture_output=True, check=False,
    )
    if result.returncode == 0:
        return [root / os.fsdecode(value) for value in result.stdout.split(b"\0") if value]
    return [path for path in root.rglob("*") if path.is_file() and ".git" not in path.relative_to(root).parts]


def scan(root: Path) -> list[str]:
    root = root.resolve()
    problems: list[str] = []
    for path in _tracked(root):
        relative = path.relative_to(root)
        name = relative.as_posix()
        if FORBIDDEN_PARTS.intersection(relative.parts):
            problems.append(f"forbidden directory: {name}")
            continue
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        if path.is_symlink() or attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            problems.append(f"link/reparse point: {name}")
            continue
        if path.name not in ALLOWED_NAMES and path.suffix.lower() not in ALLOWED_SUFFIXES:
            problems.append(f"unexpected file type: {name}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            problems.append(f"non-text file: {name}")
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                problems.append(f"{label}: {name}")
    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = scan(root)
    for item in problems:
        print(item)
    print(f"Publication scan: {'FAILED' if problems else 'PASS'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
