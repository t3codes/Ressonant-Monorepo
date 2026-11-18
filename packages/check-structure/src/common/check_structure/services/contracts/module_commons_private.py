from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import StructureSettings

CONTRACT_ID = "module-commons-private"


def build(
    settings: StructureSettings,
    module_names: tuple[str, ...],
    modules_with_commons: tuple[str, ...],
) -> tuple[Contract, ...]:
    """Um contrato por módulo: `forbidden` não referencia "o mesmo módulo" por wildcard."""
    contracts = []
    for module in modules_with_commons:
        others = tuple(
            f"{settings.modules_package}.{other}" for other in module_names if other != module
        )
        if not others:
            continue
        contracts.append(
            Contract(
                id=CONTRACT_ID,
                name=f"commons do módulo {module} só é importado por ele mesmo",
                kind="forbidden",
                options={
                    "source_modules": others,
                    "forbidden_modules": (
                        f"{settings.modules_package}.{module}.{settings.module_commons}",
                    ),
                    "allow_indirect_imports": ("True",),
                },
            )
        )
    return tuple(contracts)
