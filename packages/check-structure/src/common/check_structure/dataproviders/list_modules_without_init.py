from pathlib import Path


def list_modules_without_init(
    source_root: Path, modules_package: str, exclude: tuple[str, ...], layers: tuple[str, ...]
) -> tuple[str, ...]:
    """Pastas de módulo e de layer com código Python mas sem `__init__.py` (namespace package),
    como caminho relativo a `modules_package` (`patient` ou `patient/usecases`)."""
    modules_dir = source_root.joinpath(*modules_package.split("."))
    if not modules_dir.is_dir():
        return ()
    modules = [
        entry
        for entry in modules_dir.iterdir()
        if entry.is_dir()
        and entry.name not in exclude
        and entry.name != "__pycache__"
        and not entry.name.startswith(".")
    ]
    folders = [*modules, *(module / layer for module in modules for layer in layers)]
    return tuple(
        sorted(
            folder.relative_to(modules_dir).as_posix()
            for folder in folders
            if folder.is_dir()
            and not (folder / "__init__.py").is_file()
            and any(folder.rglob("*.py"))
        )
    )
