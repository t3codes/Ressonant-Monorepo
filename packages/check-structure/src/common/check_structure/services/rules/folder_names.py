import re

from common.check_structure.common.violation import Violation
from common.check_structure.services.layer_path_service import stem

RULE_ID = "folder-names"
# `_` à frente: módulo privado (`_helpers`) ou dunder (`__main__`).
SNAKE_CASE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*$")


def check(sources: tuple[tuple[str, str], ...]) -> tuple[Violation, ...]:
    """Pastas e módulos (.py) em snake_case minúsculo. `__init__` é ignorado."""
    names: dict[str, str] = {}
    for path, _ in sources:
        parts = path.split("/")
        for depth, folder in enumerate(parts[1:-1], start=2):
            names.setdefault("/".join(parts[:depth]), folder)
        if stem(path) != "__init__":
            names[path] = stem(path)
    return tuple(
        Violation(rule=RULE_ID, path=path, message=f"`{name}` deve estar em snake_case minúsculo")
        for path, name in sorted(names.items())
        if not SNAKE_CASE.match(name)
    )
