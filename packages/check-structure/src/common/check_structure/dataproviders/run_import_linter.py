import sys
import tempfile
from pathlib import Path

from importlinter.cli import lint_imports


def run_import_linter(config_text: str, source_dir: Path | None = None) -> int:
    """`source_dir` vai à frente do sys.path para o grafo usar o pacote da app escolhida, e não
    o do cwd ou outro de mesmo nome (ex.: `app`)."""
    if source_dir is not None:
        sys.path.insert(0, str(source_dir))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "importlinter.ini"
            config_path.write_text(config_text)
            return lint_imports(config_filename=str(config_path))
    finally:
        if source_dir is not None:
            sys.path.remove(str(source_dir))
