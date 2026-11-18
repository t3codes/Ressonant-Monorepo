from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import PlatformSettings

CONTRACT_ID = "packages-no-apps"


def build(settings: PlatformSettings) -> Contract:
    return Contract(
        id=CONTRACT_ID,
        name="packages/* não importam apps",
        kind="forbidden",
        options={
            "source_modules": (settings.root_package,),
            "forbidden_modules": settings.app_packages,
            "allow_indirect_imports": ("True",),
        },
    )
