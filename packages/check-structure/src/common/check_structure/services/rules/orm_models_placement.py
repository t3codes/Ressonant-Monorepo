import ast

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation
from common.check_structure.config import defaults

RULE_ID = "orm-models-placement"


def check(
    settings: StructureSettings, sources: tuple[tuple[str, str], ...]
) -> tuple[Violation, ...]:
    common_path = settings.common_package.replace(".", "/")
    dataprovider_layer = settings.layers[-1]
    violations = []
    for path, code in sources:
        if path.startswith(f"{common_path}/") or _in_models_folder(path, dataprovider_layer):
            continue
        violations.extend(
            Violation(
                rule=RULE_ID,
                path=path,
                message=(
                    f"model ORM `{name}` fora de {dataprovider_layer}/"
                    f"{'/'.join(defaults.ORM_MODELS_PATH)} ou common"
                ),
            )
            for name in _orm_classes(code, settings.orm_bases)
        )
    return tuple(violations)


def _in_models_folder(path: str, dataprovider_layer: str) -> bool:
    expected = (dataprovider_layer, *defaults.ORM_MODELS_PATH)
    parts = path.split("/")[:-1]
    size = len(expected)
    return any(tuple(parts[i : i + size]) == expected for i in range(len(parts) - size + 1))


def _orm_classes(code: str, orm_bases: tuple[str, ...]) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name not in orm_bases
        and any(_base_name(b) in orm_bases for b in node.bases)
    ]


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
