from typing import Any

from common.check_structure.common.errors import ConfigError
from common.check_structure.common.settings import (
    ExceptionEntry,
    NamingSettings,
    PathException,
    StructureSettings,
)
from common.check_structure.config import defaults

KNOWN_KEYS = frozenset(
    {
        "root_package",
        "source_root",
        "modules_package",
        "common_package",
        "config_package",
        "layers",
        "module_commons",
        "dataclasses_dir",
        "exclude_modules",
        "extra_root_folders",
        "orm_bases",
        "disable",
        "exceptions",
        "path_exceptions",
        "naming",
    }
)


def build_settings(raw: dict[str, Any]) -> StructureSettings:
    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        # Chave com typo cairia calada no default (ex.: `orm_base` mantém o `orm_bases` padrão).
        raise ConfigError(f"Chave desconhecida em [tool.check-structure]: {', '.join(unknown)}")
    root = raw.get("root_package")
    if not root:
        raise ConfigError("`root_package` é obrigatório em [tool.check-structure].")
    layers = raw.get("layers", defaults.LAYERS)
    if (
        isinstance(layers, str)
        or len(layers) != len(defaults.LAYERS)
        or len(set(layers)) != len(layers)
        or not all(isinstance(layer, str) and layer for layer in layers)
    ):
        # As regras identificam cada layer pela posição (entrypoints, usecases, services,
        # dataproviders); `services` continua na lista mesmo quando nenhum módulo a tem.
        raise ConfigError(
            f"`layers` deve ter {len(defaults.LAYERS)} nomes distintos, "
            f"na ordem de {defaults.LAYERS}: {layers}"
        )
    return StructureSettings(
        root_package=root,
        modules_package=raw.get("modules_package", f"{root}.{defaults.MODULES_DIR}"),
        common_package=raw.get("common_package", f"{root}.{defaults.COMMON_DIR}"),
        config_package=raw.get("config_package", f"{root}.{defaults.CONFIG_DIR}"),
        layers=tuple(layers),
        module_commons=raw.get("module_commons", defaults.MODULE_COMMONS_DIR),
        dataclasses_dir=raw.get("dataclasses_dir", defaults.DATACLASSES_DIR),
        exclude_modules=tuple(raw.get("exclude_modules", ())),
        disabled_contracts=frozenset(raw.get("disable", ())),
        exceptions=tuple(_build_exception(item) for item in raw.get("exceptions", ())),
        source_root=raw.get("source_root", "."),
        extra_root_folders=tuple(raw.get("extra_root_folders", ())),
        orm_bases=tuple(raw.get("orm_bases", defaults.ORM_BASES)),
        path_exceptions=tuple(_build_path_exception(i) for i in raw.get("path_exceptions", ())),
        naming=_build_naming(raw.get("naming", {})),
    )


def _build_exception(item: dict[str, Any]) -> ExceptionEntry:
    if not isinstance(item, dict):
        raise ConfigError(f"Exceção deve ser uma tabela [[...exceptions]]: {item}")
    missing = [key for key in ("from", "to", "reason") if not item.get(key)]
    if missing:
        raise ConfigError(f"Exceção sem {', '.join(missing)}: {item}")
    return ExceptionEntry(source=item["from"], target=item["to"], reason=item["reason"])


def _build_path_exception(item: dict[str, Any]) -> PathException:
    if not isinstance(item, dict):
        raise ConfigError(f"Exceção de path deve ser uma tabela [[...path_exceptions]]: {item}")
    missing = [key for key in ("rule", "path", "reason") if not item.get(key)]
    if missing:
        raise ConfigError(f"Exceção de path sem {', '.join(missing)}: {item}")
    return PathException(rule=item["rule"], path=item["path"], reason=item["reason"])


def _build_naming(raw: dict[str, Any]) -> NamingSettings:
    try:
        return NamingSettings(**raw)
    except TypeError as error:
        raise ConfigError(f"Chave inválida em [tool.check-structure.naming]: {error}") from error
