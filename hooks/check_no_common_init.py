#!/usr/bin/env python3
"""Falha se existir packages/*/src/common/__init__.py (quebra namespace PEP 420)."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    bad: list[Path] = []
    for path in repo.glob("packages/*/src/common/__init__.py"):
        if path.is_file():
            bad.append(path)
    if bad:
        print("ERRO: __init__.py proibido em src/common/ (namespace package):", file=sys.stderr)
        for p in bad:
            print(f"  - {p.relative_to(repo)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
