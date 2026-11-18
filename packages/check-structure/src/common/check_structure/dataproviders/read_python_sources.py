from pathlib import Path


def read_python_sources(root: Path, relative_to: Path) -> tuple[tuple[str, str], ...]:
    """Retorna (caminho relativo, código) de cada .py abaixo de `root`."""
    return tuple(
        (path.relative_to(relative_to).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.py"))
    )
