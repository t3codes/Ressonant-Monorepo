from pathlib import Path

from common.check_structure.common.errors import ConfigError
from common.check_structure.common.settings import StructureSettings
from common.check_structure.dataproviders.read_pyproject import read_pyproject
from common.check_structure.services.build_settings_service import build_settings
from common.check_structure.usecases.run_import_contracts_usecase import (
    run_import_contracts_usecase,
)
from common.check_structure.usecases.run_path_checks_usecase import (
    run_path_checks_usecase,
)


def run_structure_check_usecase(pyproject: Path, strict: bool) -> int:
    """Roda imports e localização da app; só falha o exit code quando `strict`."""
    settings = build_settings(read_pyproject(pyproject))
    app_dir = pyproject.parent
    _require_packages(settings, app_dir)
    exit_code = max(
        run_import_contracts_usecase(settings, app_dir),
        run_path_checks_usecase(settings, app_dir),
    )
    return exit_code if strict else 0


def _require_packages(settings: StructureSettings, app_dir: Path) -> None:
    """Pacote inexistente faria contratos e regras não casarem com nada e passarem calados."""
    source_root = app_dir / settings.source_root
    for key in ("root_package", "modules_package"):
        package = getattr(settings, key)
        if not source_root.joinpath(*package.split(".")).is_dir():
            raise ConfigError(f"`{key}` = {package!r} não existe em {source_root}.")
