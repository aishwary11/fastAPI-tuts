"""Run the same checks CI runs, from any OS.

    python -m scripts.check              # lint, format, typecheck, test, build
    python -m scripts.check test lint    # only the named checks
    python -m scripts.check --list

Each check runs with the *current* interpreter, so what you see locally is what
CI sees (see ``.github/workflows/ci.yml``).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

# (name, module, args, description)
CHECKS: tuple[tuple[str, str, list[str], str], ...] = (
    ("lint", "ruff", ["check", "."], "Lint"),
    ("format", "ruff", ["format", "--check", "."], "Check formatting"),
    ("typecheck", "mypy", [], "Type check"),
    ("test", "pytest", ["-q"], "Run the test suite"),
    ("build", "build", [], "Build the sdist and wheel"),
)


def run(names: Sequence[str]) -> int:
    known = {name for name, *_ in CHECKS}
    unknown = sorted(set(names) - known)
    if unknown:
        print(f"unknown check(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(sorted(known))}", file=sys.stderr)
        return 2

    selected = [check for check in CHECKS if not names or check[0] in names]
    failed: list[str] = []

    for name, module, args, description in selected:
        print(f"\n=== {description} ({name}) ===", flush=True)
        completed = subprocess.run([sys.executable, "-m", module, *args], check=False)
        if completed.returncode != 0:
            failed.append(name)

    print(f"\n{'=' * 60}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(selected)} check(s) passed: {', '.join(c[0] for c in selected)}")
    return 0


def main() -> int:
    description = __doc__.splitlines()[0] if __doc__ else "Run the same checks CI runs"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("checks", nargs="*", help="checks to run (default: all)")
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the available checks and exit",
    )
    args = parser.parse_args()

    if args.list:
        for name, _module, _args, description in CHECKS:
            print(f"{name:10} {description}")
        return 0

    return run(args.checks)


if __name__ == "__main__":
    raise SystemExit(main())
