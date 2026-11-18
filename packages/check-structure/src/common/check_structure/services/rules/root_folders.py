from common.check_structure.common.settings import StructureSettings
from common.check_structure.common.violation import Violation
from common.check_structure.config import defaults

RULE_ID = "root-folders"


def check(settings: StructureSettings, root_dirs: tuple[str, ...]) -> tuple[Violation, ...]:
    required = _required_folders(settings)
    allowed = {*defaults.ROOT_FOLDERS, *required, *settings.extra_root_folders}
    extra = (
        Violation(
            rule=RULE_ID,
            path=f"{settings.root_package}/{name}",
            message=f"pasta não permitida na raiz (permitidas: {', '.join(sorted(allowed))})",
        )
        for name in root_dirs
        if name not in allowed
    )
    missing = (
        Violation(
            rule=RULE_ID,
            path=f"{settings.root_package}/{name}",
            message="pasta obrigatória ausente na raiz",
        )
        for name in required
        if name not in root_dirs
    )
    return (*extra, *missing)


def _required_folders(settings: StructureSettings) -> tuple[str, ...]:
    """commons, config e modules, com os nomes configurados; ignora o que não é filho
    direto da raiz (ex.: `modules_package` igual à própria raiz durante a migração)."""
    prefix = f"{settings.root_package}."
    packages = (settings.common_package, settings.config_package, settings.modules_package)
    return tuple(
        package.removeprefix(prefix)
        for package in packages
        if package.startswith(prefix) and "." not in package.removeprefix(prefix)
    )
