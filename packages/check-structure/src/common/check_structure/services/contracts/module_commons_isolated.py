from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import StructureSettings

CONTRACT_ID = "module-commons-isolated"


def build(
    settings: StructureSettings,
    module_names: tuple[str, ...],
    layers_by_module: dict[str, tuple[str, ...]],
) -> tuple[Contract, ...]:
    """Um contrato por módulo: os commons só dependem de common, config e deles mesmos,
    nunca das layers do próprio módulo nem de outros módulos. Recebe só os módulos que têm
    commons, cada um com as layers que existem nele."""
    prefix = settings.modules_package
    contracts = []
    for module, layers in layers_by_module.items():
        forbidden = (
            *(f"{prefix}.{module}.{layer}" for layer in layers),
            *(f"{prefix}.{other}" for other in module_names if other != module),
        )
        if not forbidden:
            continue
        contracts.append(
            Contract(
                id=CONTRACT_ID,
                name=f"commons do módulo {module} não importa layers nem outros módulos",
                kind="forbidden",
                options={
                    "source_modules": (f"{prefix}.{module}.{settings.module_commons}",),
                    "forbidden_modules": forbidden,
                    "allow_indirect_imports": ("True",),
                },
            )
        )
    return tuple(contracts)
