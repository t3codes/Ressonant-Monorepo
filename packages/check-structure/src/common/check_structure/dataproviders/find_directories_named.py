from pathlib import Path


def find_directories_named(root: Path, name: str, relative_to: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(relative_to).as_posix() for path in root.rglob(name) if path.is_dir()
        )
    )
