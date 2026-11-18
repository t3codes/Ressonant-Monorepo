from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import StructureSettings

CONTRACT_ID = "common-no-modules"


def build(settings: StructureSettings, module_names: tuple[str, ...]) -> tuple[Contract, ...]:
    """Proíbe cada módulo descoberto: proibir `modules_package` não funciona quando ele é a
    raiz da app, pois o import-linter ignora o destino que contém a própria origem."""
    if not module_names:
        return ()
    return (
        Contract(
            id=CONTRACT_ID,
            name="common não importa módulos de negócio",
            kind="forbidden",
            options={
                "source_modules": (settings.common_package,),
                "forbidden_modules": tuple(
                    f"{settings.modules_package}.{module}" for module in module_names
                ),
                "allow_indirect_imports": ("True",),
            },
        ),
    )
