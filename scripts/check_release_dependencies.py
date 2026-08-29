#!/usr/bin/env python3
"""Fail closed when release-only dependencies do not match their exact pins."""

from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import re
import sys
from typing import Callable, Sequence


def read_exact_pin(requirements: Path, package: str) -> str:
    """Return one exact ``package==version`` pin or raise a useful error."""

    exact = re.compile(r"{}==([^\s;]+)".format(re.escape(package)), re.IGNORECASE)
    candidates: list[str] = []
    invalid: list[str] = []
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if re.match(r"{}(?:\b|\[)".format(re.escape(package)), line, re.IGNORECASE):
            match = exact.fullmatch(line)
            if match is None:
                invalid.append(line)
            else:
                candidates.append(match.group(1))

    if invalid:
        raise RuntimeError(
            "{} must be an unconditional exact pin in {} (found: {})".format(
                package,
                requirements,
                ", ".join(invalid),
            )
        )
    if len(candidates) != 1:
        raise RuntimeError(
            "{} must have exactly one package==version pin in {} (found {})".format(
                package,
                requirements,
                len(candidates),
            )
        )
    return candidates[0]


def verify_exact_dependency(
    requirements: Path,
    package: str,
    *,
    version_reader: Callable[[str], str] = metadata.version,
) -> tuple[str, str]:
    """Verify the selected interpreter has the exact release dependency pin."""

    expected = read_exact_pin(requirements, package)
    try:
        observed = version_reader(package)
    except metadata.PackageNotFoundError as error:
        raise RuntimeError(
            "{} is not installed in {} (required {})".format(
                package,
                sys.executable,
                expected,
            )
        ) from error
    if observed != expected:
        raise RuntimeError(
            "{} {} is installed in {}, but {} pins {}".format(
                package,
                observed,
                sys.executable,
                requirements,
                expected,
            )
        )
    return expected, observed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        required=True,
        help="requirements file containing exact release dependency pins",
    )
    parser.add_argument("packages", nargs="+", help="distribution names to verify")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        for package in arguments.packages:
            expected, _observed = verify_exact_dependency(
                arguments.requirements,
                package,
            )
            print("release dependency: {}=={} ({})".format(package, expected, sys.executable))
    except (OSError, RuntimeError) as error:
        print("error: {}".format(error), file=sys.stderr)
        print(
            "hint: {} -m pip install -r {}".format(
                sys.executable,
                arguments.requirements,
            ),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
