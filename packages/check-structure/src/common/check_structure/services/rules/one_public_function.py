import ast

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation
from common.check_structure.config import defaults
from common.check_structure.services.layer_path_service import is_init, locate_layer

RULE_ID = "one-public-function"
USECASES_INDEX = 1
DATAPROVIDERS_INDEX = 3


def check(
    settings: StructureSettings, sources: tuple[tuple[str, str], ...]
) -> tuple[Violation, ...]:
    violations = []
    for path, code in sources:
        if is_init(path) or not _is_scoped(settings, path):
            continue
        names = _public_functions(code)
        if names is not None and len(names) != 1:
            violations.append(
                Violation(
                    rule=RULE_ID,
                    path=path,
                    message=f"{len(names)} funções públicas (esperada 1): {', '.join(names)}",
                )
            )
    return tuple(violations)


def _is_scoped(settings: StructureSettings, path: str) -> bool:
    located = locate_layer(path, settings.layers)
    if located is None:
        return False
    index, below = located
    if settings.dataclasses_dir in below or settings.naming.schemas_dir in below:
        return False
    if index == USECASES_INDEX:
        return True
    return index == DATAPROVIDERS_INDEX and not _in_orm_models(below)


def _in_orm_models(below: tuple[str, ...]) -> bool:
    """Só `repository/models` (models ORM) é isento; outras pastas `models` seguem a regra."""
    return below[: len(defaults.ORM_MODELS_PATH)] == defaults.ORM_MODELS_PATH


def _public_functions(code: str) -> list[str] | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not node.name.startswith("_")
    ]
