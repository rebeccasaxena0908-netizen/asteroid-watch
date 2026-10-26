# Development tooling: how it works

Added in v2 Phase 0. None of this changes what the pipeline does. It checks the code before it reaches GitHub.

## pyproject.toml

`pyproject.toml` is the single file that describes the project. It holds the name, version, dependencies (runtime and `dev`), and the settings for pytest, ruff and mypy. `make install` runs `pip install -e ".[dev]"`, which installs everything and makes `pipeline` importable from any directory. (`-e` means "editable": the installed package points to this folder, so code changes take effect immediately.)

`requirements.txt` is **generated** from it by `make requirements` (`scripts/gen_requirements.py`) for anyone who installs with `pip install -r`. A test and a pre-commit hook fail if the two differ, so they can't drift apart.

## ruff (lint)

`ruff check .` looks for likely bugs and untidy code: unused imports or variables, undefined names, unsorted imports, outdated syntax, and common mistakes (the "bugbear" rules). The rule groups are listed in `pyproject.toml`.

Ruff can also reformat code (`ruff format`). It's deliberately **not** applied to the v1 code: doing so would rewrite about 700 lines with no change in behaviour, and the v1 code is what the report describes.

## mypy (type check)

`mypy` reads the type hints (`str`, `dict | None`, …) and reports code that uses a value of the wrong type. It runs in non-strict mode for now: it checks the hints that exist without requiring them everywhere. In Phase 0 it found 5 places where the hints were wrong or incomplete, for example `diameter_m()` receiving `None` while its hint said `dict`. These were fixed, and behaviour stayed the same.

## pre-commit (git hooks)

`make hooks` installs a git hook. On every `git commit`, it runs four checks on the staged files and stops the commit if one fails:

| Hook | What it checks |
|---|---|
| secret scan | No staged file contains a secret (see below) |
| requirements in sync | `requirements.txt` matches `pyproject.toml` |
| ruff | Lint |
| mypy | Type check |

The hooks run the tools already in `.venv` (`language: system`), so they use the same versions as `pyproject.toml` and download nothing.

## Secret scan (`scripts/check_secrets.py`)

1. It reads `.env` and collects the values of variables whose names contain KEY, PASSWORD, SECRET or TOKEN. Placeholders such as `change_me` and very short values are skipped.
2. It searches each staged file for those exact values. This catches a leaked secret whatever its format.
3. It also searches for credential patterns: `api_key=` followed by a long value (NASA puts the key in response URLs), private-key headers, and GitHub tokens. This catches secrets that aren't in this machine's `.env`.

It prints only the variable or pattern name and the file, never the secret. `make scan-secrets` runs the same check on every tracked file.

## GitHub Actions (CI)

`.github/workflows/tests.yml` runs on every push. On a fresh Ubuntu machine with Python 3.14 and PHP 8.2, it installs the project and runs ruff, mypy, the requirements check, the pattern-based secret scan and the offline tests. CI has no `.env` and no database, which also proves the tests don't need either. It's free for public repositories.
