from pathlib import Path


def find_missing_modules(source_root: Path, modules: tuple[str, ...]) -> frozenset[str]:
    """Módulos que não existem como pacote (`__init__.py`) nem como arquivo `.py`."""
    return frozenset(
        module
        for module in modules
        if not (source_root.joinpath(*module.split(".")) / "__init__.py").is_file()
        and not source_root.joinpath(*module.split(".")).with_suffix(".py").is_file()
    )
