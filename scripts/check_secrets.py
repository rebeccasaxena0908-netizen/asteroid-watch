"""Refuse a commit if a file contains a secret (run by pre-commit on every commit).

Two checks:
1. The real values of the secret variables in .env (names containing KEY, PASSWORD,
   SECRET or TOKEN). This catches a leaked value whatever it looks like.
2. Patterns that look like credentials, for secrets that aren't in this machine's .env
   (e.g. an api_key=... URL copied from a NASA response before redaction).

Only the variable or pattern name and the file are printed, never the secret itself.

Usage: python -m scripts.check_secrets [files...]   (no files: the staged files)
"""

import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
SECRET_NAME = re.compile(r"KEY|PASSWORD|SECRET|TOKEN")
PLACEHOLDERS = {"your_key_here", "change_me", "DEMO_KEY"}
MIN_SECRET_LENGTH = 8  # shorter values would match ordinary text
PATTERNS = {
    "api_key in a URL": re.compile(r"api_key=(?!REDACTED|DEMO_KEY|your_key_here)[A-Za-z0-9]{20,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}"),
}


def env_secrets(env_file: Path) -> dict[str, str]:
    """{variable name: value} for the secret variables in env_file that hold a real value."""
    if not env_file.exists():
        return {}
    return {
        name: value
        for name, value in dotenv_values(env_file).items()
        if SECRET_NAME.search(name) and value and value not in PLACEHOLDERS and len(value) >= MIN_SECRET_LENGTH
    }


def find_secrets(text: str, secrets: dict[str, str]) -> list[str]:
    """Names of the secrets and patterns found in text."""
    found = [name for name, value in secrets.items() if value in text]
    found += [name for name, pattern in PATTERNS.items() if pattern.search(text)]
    return found


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, check=True, cwd=ROOT,
    )
    return out.stdout.split()


def main(argv: list[str]) -> int:
    secrets = env_secrets(ROOT / ".env")
    problems = []
    for name in argv or staged_files():
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="ignore")
        problems += [f"{name}: contains {what}" for what in find_secrets(text, secrets)]
    for problem in problems:
        print(problem)
    if problems:
        print("Commit refused: remove the secret (use .env) and try again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
