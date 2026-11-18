import ast

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.sources import Sources
from common.check_structure.common.violation import Violation
from common.check_structure.services.layer_path_service import locate_layer

RULE_ID = "dataclasses-pure"


def check(settings: StructureSettings, sources: Sources) -> tuple[Violation, ...]:
    """Dataclasses só importam commons (global ou do próprio módulo) e dataclasses do próprio
    módulo, da mesma layer ou de uma abaixo. Regra por allowlist: um contrato `forbidden`
    deixaria passar a própria layer e a raiz de outros módulos."""
    known_modules = _known_modules(sources)
    violations = []
    for path, code in sources:
        if settings.dataclasses_dir not in path.split("/")[:-1]:
            continue
        violations.extend(
            Violation(
                rule=RULE_ID,
                path=path,
                message=f"importa `{target}` (só commons e dataclasses permitidas)",
            )
            for target in _app_imports(settings.root_package, path, code, known_modules)
            if not _is_allowed(settings, path, target)
        )
    return tuple(violations)


def _known_modules(sources: Sources) -> frozenset[str]:
    """Módulos e pacotes da app, para distinguir `from A import submodulo` de um símbolo."""
    modules = set()
    for path, _ in sources:
        parts = path.removesuffix(".py").split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.update(".".join(parts[:size]) for size in range(1, len(parts) + 1))
    return frozenset(modules)


def _app_imports(
    root_package: str, path: str, code: str, known_modules: frozenset[str]
) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    package = path.split("/")[:-1]
    targets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            targets += _import_from_targets(node, package, known_modules)
    return [t for t in targets if _is_within(t, root_package)]


def _import_from_targets(
    node: ast.ImportFrom, package: list[str], known_modules: frozenset[str]
) -> list[str]:
    """Resolve imports relativos e trata `from A import B` como `A.B` quando B é submódulo."""
    base = package[: len(package) - node.level + 1] if node.level else []
    module = ".".join([*base, *node.module.split(".")] if node.module else base)
    submodules = (f"{module}.{alias.name}" for alias in node.names)
    return [submodule if submodule in known_modules else module for submodule in submodules]


def _is_allowed(settings: StructureSettings, path: str, target: str) -> bool:
    if _is_within(target, settings.common_package):
        return True
    module = _module_of(settings, path.removesuffix(".py").replace("/", "."))
    if module is None:
        return False
    module_package = f"{settings.modules_package}.{module}"
    if _is_within(target, f"{module_package}.{settings.module_commons}"):
        return True
    if not _is_within(target, module_package) or settings.dataclasses_dir not in target.split("."):
        return False
    source_layer = locate_layer(path, settings.layers)
    target_layer = locate_layer(f"{target.replace('.', '/')}/__init__.py", settings.layers)
    return (
        source_layer is not None and target_layer is not None and target_layer[0] >= source_layer[0]
    )


def _module_of(settings: StructureSettings, dotted: str) -> str | None:
    prefix = f"{settings.modules_package}."
    if not dotted.startswith(prefix):
        return None
    module = dotted.removeprefix(prefix).split(".", 1)[0]
    return None if module in settings.exclude_modules else module


def _is_within(target: str, package: str) -> bool:
    return target == package or target.startswith(f"{package}.")
