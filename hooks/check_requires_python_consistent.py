#!/usr/bin/env python3
"""Garante requires-python == ==3.13.* em todo pyproject.toml (raiz, packages, apps)."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

EXPECTED = "==3.13.*"


def iter_pyprojects(repo: Path) -> list[Path]:
    paths = [repo / "pyproject.toml"]
    paths.extend(sorted(repo.glob("packages/**/pyproject.toml")))
    paths.extend(sorted(repo.glob("apps/**/pyproject.toml")))
    return [p for p in paths if p.is_file()]


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    errors: list[str] = []
    for path in iter_pyprojects(repo):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        proj = data.get("project") or {}
        rp = proj.get("requires-python")
        rel = path.relative_to(repo)
        if rp is None:
            errors.append(f"{rel}: falta [project].requires-python")
        elif rp != EXPECTED:
            errors.append(f"{rel}: requires-python é {rp!r}, esperado {EXPECTED!r}")
    if errors:
        print("ERRO: requires-python inconsistente:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
