from pathlib import Path

from common.check_structure.dataproviders.read_pyproject import read_pyproject
from common.check_structure.dataproviders.run_import_linter import run_import_linter
from common.check_structure.services.build_platform_settings_service import (
    build_platform_settings,
)
from common.check_structure.services.contracts import packages_no_apps
from common.check_structure.services.render_importlinter_config_service import (
    render_importlinter_config,
)


def run_platform_check_usecase(pyproject: Path, strict: bool) -> int:
    """Roda os contratos de isolamento dos packages/*; só falha o exit code quando `strict`."""
    settings = build_platform_settings(read_pyproject(pyproject))
    config = render_importlinter_config(
        settings.root_package,
        (packages_no_apps.build(settings),),
        include_external_packages=True,
    )
    exit_code = run_import_linter(config)
    return exit_code if strict else 0
