from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.sources import Sources
from common.check_structure.common.violation import Violation
from common.check_structure.services.rules import (
    class_names,
    file_names,
    folder_names,
    one_public_function,
    query_objects,
)


def run_naming_check_usecase(
    settings: StructureSettings, sources: Sources
) -> tuple[Violation, ...]:
    rules = {
        file_names.RULE_ID: lambda: file_names.check(settings, sources),
        one_public_function.RULE_ID: lambda: one_public_function.check(settings, sources),
        class_names.RULE_ID: lambda: class_names.check(settings, sources),
        query_objects.RULE_ID: lambda: query_objects.check(settings, sources),
        folder_names.RULE_ID: lambda: folder_names.check(sources),
    }
    return tuple(
        violation
        for rule_id, run in rules.items()
        if rule_id not in settings.disabled_contracts
        for violation in run()
    )
