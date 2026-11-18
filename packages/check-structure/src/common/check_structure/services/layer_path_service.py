def locate_layer(path: str, layers: tuple[str, ...]) -> tuple[int, tuple[str, ...]] | None:
    """Índice da layer do arquivo e as pastas abaixo dela, ou None se estiver fora das layers."""
    parts = path.split("/")[:-1]
    for position, part in enumerate(parts):
        if part in layers:
            return layers.index(part), tuple(parts[position + 1 :])
    return None


def is_init(path: str) -> bool:
    return path.endswith("/__init__.py")


def stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".py")
