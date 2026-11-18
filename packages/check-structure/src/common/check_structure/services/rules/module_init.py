from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation

RULE_ID = "module-init"


def check(
    settings: StructureSettings, modules_without_init: tuple[str, ...]
) -> tuple[Violation, ...]:
    modules_path = settings.modules_package.replace(".", "/")
    return tuple(
        Violation(
            rule=RULE_ID,
            path=f"{modules_path}/{folder}",
            message=f"{'layer' if '/' in folder else 'módulo'} sem __init__.py: "
            "fica fora de todas as checagens de import",
        )
        for folder in modules_without_init
    )
