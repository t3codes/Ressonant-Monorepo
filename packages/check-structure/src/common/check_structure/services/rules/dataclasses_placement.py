from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation

RULE_ID = "dataclasses-placement"


def check(settings: StructureSettings, dataclasses_dirs: tuple[str, ...]) -> tuple[Violation, ...]:
    common_path = settings.common_package.replace(".", "/")
    return tuple(
        Violation(
            rule=RULE_ID,
            path=path,
            message="`dataclasses` só pode ficar dentro de uma layer ou de common",
        )
        for path in dataclasses_dirs
        if not _is_allowed(path, common_path, settings.layers)
    )


def _is_allowed(path: str, common_path: str, layers: tuple[str, ...]) -> bool:
    if path.startswith(f"{common_path}/"):
        return True
    return any(part in layers for part in path.split("/")[:-1])
