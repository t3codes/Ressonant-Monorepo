import tomllib
from pathlib import Path
from typing import Any

from common.check_structure.common.errors import ConfigError

TOOL_KEY = "check-structure"


def read_pyproject(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"{path} não encontrado.")
    with path.open("rb") as file:
        data = tomllib.load(file)
    section = data.get("tool", {}).get(TOOL_KEY)
    if section is None:
        raise ConfigError(f"Seção [tool.{TOOL_KEY}] ausente em {path}.")
    return section
