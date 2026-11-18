from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import StructureSettings
from common.check_structure.services.contracts import (
    common_no_modules,
    config_isolated,
    layers,
    module_commons_isolated,
    module_commons_private,
)


def build_contracts(
    settings: StructureSettings,
    module_names: tuple[str, ...],
    modules_with_commons: tuple[str, ...],
    commons_layers: dict[str, tuple[str, ...]],
) -> tuple[Contract, ...]:
    contracts = (
        *layers.build(settings),
        *common_no_modules.build(settings, module_names),
        config_isolated.build(settings, module_names),
        *module_commons_private.build(settings, module_names, modules_with_commons),
        *module_commons_isolated.build(settings, module_names, commons_layers),
    )
    return tuple(c for c in contracts if c.id not in settings.disabled_contracts)
