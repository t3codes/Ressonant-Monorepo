import ast

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.sources import Sources
from common.check_structure.common.violation import Violation
from common.check_structure.config import defaults
from common.check_structure.services.layer_path_service import is_init, locate_layer, stem

RULE_ID = "query-objects"


def check(settings: StructureSettings, sources: Sources) -> tuple[Violation, ...]:
    """QueryObject é exclusivo da layer de dataproviders."""
    violations = []
    for path, code in sources:
        in_dataproviders = _in_dataproviders(settings, path)
        if (
            not in_dataproviders
            and not is_init(path)
            and stem(path).endswith(settings.naming.query_object_suffix)
        ):
            violations.append(
                Violation(RULE_ID, path, "arquivo `_query_object` só pode ficar em dataproviders")
            )
        for node in _query_object_classes(code):
            if not in_dataproviders:
                message = f"`{node.name}` só pode ficar em dataproviders"
                violations.append(Violation(RULE_ID, path, message))
    return tuple(violations)


def _in_dataproviders(settings: StructureSettings, path: str) -> bool:
    located = locate_layer(path, settings.layers)
    return located is not None and located[0] == len(settings.layers) - 1


def _query_object_classes(code: str) -> list[ast.ClassDef]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name.endswith(defaults.QUERY_OBJECT_CLASS_SUFFIX)
    ]
