from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation
from common.check_structure.services.layer_path_service import is_init, locate_layer, stem

RULE_ID = "file-names"


def check(
    settings: StructureSettings, sources: tuple[tuple[str, str], ...]
) -> tuple[Violation, ...]:
    violations = []
    for path, _ in sources:
        if is_init(path):
            continue
        expected = _expected_suffixes(settings, path)
        if expected and not stem(path).endswith(expected):
            violations.append(
                Violation(
                    rule=RULE_ID,
                    path=path,
                    message=f"nome deve terminar em {' ou '.join(expected)}",
                )
            )
    return tuple(violations)


def _expected_suffixes(settings: StructureSettings, path: str) -> tuple[str, ...]:
    naming = settings.naming
    folders = path.split("/")[:-1]
    if naming.schemas_dir in folders:
        return (naming.schema_suffix,)
    if settings.dataclasses_dir in folders:
        return (naming.dto_suffix, naming.query_object_suffix)
    located = locate_layer(path, settings.layers)
    if located is None:
        return ()
    index, below = located
    if index == 0:
        if naming.rest_dir in below:
            return (naming.router_suffix,)
        if naming.messaging_dir in below:
            return (naming.consumer_suffix,)
    elif index == 1:
        return (naming.usecase_suffix,)
    elif index == 2:
        return (naming.service_suffix,)
    return ()
