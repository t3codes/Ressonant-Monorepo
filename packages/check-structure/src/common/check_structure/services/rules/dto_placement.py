import ast

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.sources import Sources
from common.check_structure.common.violation import Violation
from common.check_structure.config import defaults

RULE_ID = "dto-placement"


def check(settings: StructureSettings, sources: Sources) -> tuple[Violation, ...]:
    """Classe pública terminada em DTO só pode ser declarada dentro de uma pasta dataclasses."""
    violations = []
    for path, code in sources:
        if settings.dataclasses_dir in path.split("/")[:-1]:
            continue
        violations.extend(
            Violation(
                rule=RULE_ID,
                path=path,
                message=f"`{name}` deve ser declarado em {settings.dataclasses_dir}/",
            )
            for name in _public_dtos(code)
        )
    return tuple(violations)


def _public_dtos(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name.endswith(defaults.DTO_CLASS_SUFFIX)
        and not node.name.startswith("_")
    ]
