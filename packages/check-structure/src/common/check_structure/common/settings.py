from dataclasses import dataclass, field

from common.check_structure.config import defaults


@dataclass(frozen=True)
class ExceptionEntry:
    source: str
    target: str
    reason: str


@dataclass(frozen=True)
class NamingSettings:
    usecase_suffix: str = defaults.USECASE_SUFFIX
    service_suffix: str = defaults.SERVICE_SUFFIX
    router_suffix: str = defaults.ROUTER_SUFFIX
    consumer_suffix: str = defaults.CONSUMER_SUFFIX
    dto_suffix: str = defaults.DTO_SUFFIX
    query_object_suffix: str = defaults.QUERY_OBJECT_SUFFIX
    schema_suffix: str = defaults.SCHEMA_SUFFIX
    rest_dir: str = defaults.REST_DIR
    messaging_dir: str = defaults.MESSAGING_DIR
    schemas_dir: str = defaults.SCHEMAS_DIR
    model_suffix: str = defaults.MODEL_SUFFIX


@dataclass(frozen=True)
class PathException:
    rule: str
    path: str
    reason: str


@dataclass(frozen=True)
class StructureSettings:
    root_package: str
    modules_package: str
    common_package: str
    config_package: str
    layers: tuple[str, ...]
    module_commons: str
    dataclasses_dir: str
    exclude_modules: tuple[str, ...] = ()
    disabled_contracts: frozenset[str] = frozenset()
    exceptions: tuple[ExceptionEntry, ...] = field(default_factory=tuple)
    source_root: str = "."
    extra_root_folders: tuple[str, ...] = ()
    orm_bases: tuple[str, ...] = ()
    path_exceptions: tuple[PathException, ...] = ()
    naming: NamingSettings = field(default_factory=NamingSettings)


@dataclass(frozen=True)
class PlatformSettings:
    root_package: str
    app_packages: tuple[str, ...]
