from pathlib import Path


def list_module_layers(
    source_root: Path, modules_package: str, modules: tuple[str, ...], layers: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    """Layers que existem como pacote em cada módulo (`services` é opcional)."""
    modules_dir = source_root.joinpath(*modules_package.split("."))
    return {
        module: tuple(
            layer for layer in layers if (modules_dir / module / layer / "__init__.py").is_file()
        )
        for module in modules
    }
