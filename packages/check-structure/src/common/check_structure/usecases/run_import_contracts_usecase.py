from pathlib import Path

from common.check_structure.common.settings import StructureSettings
from common.check_structure.dataproviders.find_missing_modules import find_missing_modules
from common.check_structure.dataproviders.list_module_layers import list_module_layers
from common.check_structure.dataproviders.list_module_names import list_module_names
from common.check_structure.dataproviders.list_modules_with_commons import (
    list_modules_with_commons,
)
from common.check_structure.dataproviders.run_import_linter import run_import_linter
from common.check_structure.services.build_contracts_service import build_contracts
from common.check_structure.services.drop_missing_sources_service import (
    drop_missing_sources,
    literal_sources,
)
from common.check_structure.services.render_importlinter_config_service import (
    render_importlinter_config,
)


def run_import_contracts_usecase(settings: StructureSettings, app_dir: Path) -> int:
    module_names = list_module_names(
        app_dir / settings.source_root, settings.modules_package, settings.exclude_modules
    )
    modules_with_commons = list_modules_with_commons(
        app_dir / settings.source_root,
        settings.modules_package,
        module_names,
        settings.module_commons,
    )
    commons_layers = list_module_layers(
        app_dir / settings.source_root,
        settings.modules_package,
        modules_with_commons,
        settings.layers,
    )
    contracts = build_contracts(settings, module_names, modules_with_commons, commons_layers)
    missing = find_missing_modules(app_dir / settings.source_root, literal_sources(contracts))
    contracts, warnings = drop_missing_sources(contracts, missing)
    for warning in warnings:
        print(f"AVISO: {warning}")
    config = render_importlinter_config(settings.root_package, contracts, settings.exceptions)
    exit_code = run_import_linter(config, app_dir / settings.source_root) if contracts else 0
    return max(exit_code, 1 if warnings else 0)
