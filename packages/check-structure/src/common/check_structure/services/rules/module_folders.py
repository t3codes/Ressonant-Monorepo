from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation

RULE_ID = "module-folders"


def check(
    settings: StructureSettings, folders_by_module: dict[str, tuple[str, ...]]
) -> tuple[Violation, ...]:
    allowed = {*settings.layers, settings.module_commons}
    modules_path = settings.modules_package.replace(".", "/")
    return tuple(
        Violation(
            rule=RULE_ID,
            path=f"{modules_path}/{module}/{folder}",
            message=f"pasta fora das layers (permitidas: {', '.join(sorted(allowed))})",
        )
        for module, folders in folders_by_module.items()
        for folder in folders
        if folder not in allowed
    )
