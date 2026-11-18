from pathlib import Path

from common.check_structure.common.settings import StructureSettings
from common.check_structure.dataproviders.read_python_sources import read_python_sources
from common.check_structure.services.apply_path_exceptions_service import apply_path_exceptions
from common.check_structure.services.render_violations_service import render_violations
from common.check_structure.usecases.run_location_check_usecase import run_location_check_usecase
from common.check_structure.usecases.run_naming_check_usecase import run_naming_check_usecase


def run_path_checks_usecase(settings: StructureSettings, app_dir: Path) -> int:
    """Localização e nomenclatura de arquivos e pastas; imprime o relatório agrupado."""
    source_root = app_dir / settings.source_root
    root_dir = source_root.joinpath(*settings.root_package.split("."))
    sources = read_python_sources(root_dir, source_root)
    violations = apply_path_exceptions(
        (
            *run_location_check_usecase(settings, source_root, root_dir, sources),
            *run_naming_check_usecase(settings, sources),
        ),
        settings.path_exceptions,
    )
    print(render_violations(violations))
    return 1 if violations else 0
