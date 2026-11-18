from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import StructureSettings

CONTRACT_ID = "layers"


def build(settings: StructureSettings) -> tuple[Contract, ...]:
    """Uma layer não importa as de cima. O contrato `layers` do import-linter não aceita
    wildcard de módulo, então cada layer vira um `forbidden` (vale dentro e entre módulos)."""
    prefix = settings.modules_package
    return tuple(
        Contract(
            id=CONTRACT_ID,
            name=f"{layer} não importa {', '.join(above)}",
            kind="forbidden",
            options={
                "source_modules": (f"{prefix}.*.{layer}",),
                "forbidden_modules": tuple(f"{prefix}.*.{up}" for up in above),
                "allow_indirect_imports": ("True",),
            },
        )
        for index, layer in enumerate(settings.layers)
        if (above := settings.layers[:index])
    )
