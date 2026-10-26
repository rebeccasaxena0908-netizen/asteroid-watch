"""Write requirements.txt from pyproject.toml.

pyproject.toml is the one place where dependencies are listed. requirements.txt is kept
for anyone who installs with `pip install -r requirements.txt`; a test and a pre-commit
hook check that it hasn't drifted.

Usage: python -m scripts.gen_requirements          (write the file)
       python -m scripts.gen_requirements --check  (exit 1 if it is out of date)
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"


def render(pyproject: dict) -> str:
    project = pyproject["project"]
    lines = [
        "# Generated from pyproject.toml by `make requirements`. Do not edit by hand.",
        "",
        "# runtime",
        *project["dependencies"],
        "",
        "# development: tests, lint, type checks, git hooks",
        *project["optional-dependencies"]["dev"],
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    expected = render(tomllib.loads(PYPROJECT.read_text()))
    if "--check" in argv:
        if not REQUIREMENTS.exists() or REQUIREMENTS.read_text() != expected:
            print("requirements.txt is out of date: run `make requirements`")
            return 1
        return 0
    REQUIREMENTS.write_text(expected)
    print(f"Wrote {REQUIREMENTS.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
