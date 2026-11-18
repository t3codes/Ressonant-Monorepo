from pathlib import Path


def list_module_names(
    source_root: Path, modules_package: str, exclude: tuple[str, ...]
) -> tuple[str, ...]:
    modules_dir = source_root.joinpath(*modules_package.split("."))
    if not modules_dir.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in modules_dir.iterdir()
            if (entry / "__init__.py").is_file() and entry.name not in exclude
        )
    )
