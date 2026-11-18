from pathlib import Path

from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.sources import Sources
from common.check_structure.common.violation import Violation
from common.check_structure.dataproviders.find_directories_named import find_directories_named
from common.check_structure.dataproviders.list_module_names import list_module_names
from common.check_structure.dataproviders.list_modules_without_init import (
    list_modules_without_init,
)
from common.check_structure.dataproviders.list_subdirectories import list_subdirectories
from common.check_structure.services.rules import (
    dataclasses_placement,
    dataclasses_pure,
    dto_placement,
    module_folders,
    module_init,
    orm_models_placement,
    root_folders,
)


def run_location_check_usecase(
    settings: StructureSettings, source_root: Path, root_dir: Path, sources: Sources
) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    if _enabled(settings, root_folders.RULE_ID):
        violations += root_folders.check(settings, list_subdirectories(root_dir))
    if _enabled(settings, module_folders.RULE_ID):
        modules_dir = source_root.joinpath(*settings.modules_package.split("."))
        names = list_module_names(source_root, settings.modules_package, settings.exclude_modules)
        folders = {name: list_subdirectories(modules_dir / name) for name in names}
        violations += module_folders.check(settings, folders)
    if _enabled(settings, module_init.RULE_ID):
        names = list_modules_without_init(
            source_root, settings.modules_package, settings.exclude_modules, settings.layers
        )
        violations += module_init.check(settings, names)
    if _enabled(settings, dataclasses_placement.RULE_ID):
        found = find_directories_named(root_dir, settings.dataclasses_dir, source_root)
        violations += dataclasses_placement.check(settings, found)
    if _enabled(settings, dataclasses_pure.RULE_ID):
        violations += dataclasses_pure.check(settings, sources)
    if _enabled(settings, dto_placement.RULE_ID):
        violations += dto_placement.check(settings, sources)
    if _enabled(settings, orm_models_placement.RULE_ID):
        violations += orm_models_placement.check(settings, sources)
    return tuple(violations)


def _enabled(settings: StructureSettings, rule_id: str) -> bool:
    return rule_id not in settings.disabled_contracts
