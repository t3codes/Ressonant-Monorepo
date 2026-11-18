import ast

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation
from common.check_structure.config import defaults
from common.check_structure.services.layer_path_service import stem

RULE_ID = "class-names"
# Enums auxiliares do DTO podem morar no mesmo arquivo, sem o sufixo `DTO`.
DTO_ALLOWED_BASES = ("StrEnum",)


def check(
    settings: StructureSettings, sources: tuple[tuple[str, str], ...]
) -> tuple[Violation, ...]:
    violations = []
    for path, code in sources:
        for node in _classes(code):
            expected = _expected_suffix(settings, path, node)
            if expected and not node.name.endswith(expected):
                violations.append(
                    Violation(
                        rule=RULE_ID,
                        path=path,
                        message=f"classe `{node.name}` deve terminar em {expected}",
                    )
                )
    return tuple(violations)


def _classes(code: str) -> list[ast.ClassDef]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    # Só classes de topo: aninhadas (ex.: `class Config` de um Schema) não seguem o sufixo.
    return [node for node in tree.body if isinstance(node, ast.ClassDef)]


def _expected_suffix(settings: StructureSettings, path: str, node: ast.ClassDef) -> str | None:
    if node.name.startswith("_") or node.name in settings.orm_bases:
        return None
    if _is_orm(node, settings.orm_bases):
        return settings.naming.model_suffix
    file_stem = stem(path)
    if file_stem.endswith(settings.naming.dto_suffix):
        is_enum = any(_base_name(base) in DTO_ALLOWED_BASES for base in node.bases)
        return None if is_enum else defaults.DTO_CLASS_SUFFIX
    if file_stem.endswith(settings.naming.query_object_suffix):
        return defaults.QUERY_OBJECT_CLASS_SUFFIX
    if file_stem.endswith(settings.naming.schema_suffix):
        return defaults.SCHEMA_CLASS_SUFFIX
    return None


def _is_orm(node: ast.ClassDef, orm_bases: tuple[str, ...]) -> bool:
    return any(_base_name(base) in orm_bases for base in node.bases)


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
