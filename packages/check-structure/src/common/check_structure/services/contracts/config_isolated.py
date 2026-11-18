from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import StructureSettings

CONTRACT_ID = "config-isolated"


def build(settings: StructureSettings, module_names: tuple[str, ...]) -> Contract:
    """Módulos proibidos um a um pelo mesmo motivo de `common_no_modules`."""
    return Contract(
        id=CONTRACT_ID,
        name="config não importa módulos de negócio nem common",
        kind="forbidden",
        options={
            "source_modules": (settings.config_package,),
            "forbidden_modules": (
                *(f"{settings.modules_package}.{module}" for module in module_names),
                settings.common_package,
            ),
            "allow_indirect_imports": ("True",),
        },
    )
