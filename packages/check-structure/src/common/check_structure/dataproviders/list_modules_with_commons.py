from pathlib import Path


def list_modules_with_commons(
    source_root: Path, modules_package: str, module_names: tuple[str, ...], commons_dir: str
) -> tuple[str, ...]:
    modules_dir = source_root.joinpath(*modules_package.split("."))
    return tuple(name for name in module_names if (modules_dir / name / commons_dir).is_dir())
