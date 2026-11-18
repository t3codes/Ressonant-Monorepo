import argparse
import sys
from pathlib import Path

from common.check_structure.common.errors import ConfigError
from common.check_structure.usecases.run_platform_check_usecase import run_platform_check_usecase
from common.check_structure.usecases.run_structure_check_usecase import (
    run_structure_check_usecase,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="check-structure", description="Valida imports, localização e nomes da app."
    )
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--strict", action="store_true", help="Exit 1 em caso de violação.")
    parser.add_argument(
        "--platform", action="store_true", help="Valida packages/* (raiz do workspace)."
    )
    args = parser.parse_args(argv)
    check = run_platform_check_usecase if args.platform else run_structure_check_usecase
    try:
        sys.exit(check(args.pyproject.resolve(), args.strict))
    except ConfigError as error:
        sys.exit(f"check-structure: {error}")
