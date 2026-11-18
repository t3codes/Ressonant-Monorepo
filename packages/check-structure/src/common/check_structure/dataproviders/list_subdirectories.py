from pathlib import Path


def list_subdirectories(directory: Path) -> tuple[str, ...]:
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in directory.iterdir()
            if entry.is_dir() and entry.name != "__pycache__" and not entry.name.startswith(".")
        )
    )
