from typing import Any

from common.check_structure.common.errors import ConfigError
from common.check_structure.common.settings import PlatformSettings


def build_platform_settings(raw: dict[str, Any]) -> PlatformSettings:
    platform = raw.get("platform", {})
    root, apps = platform.get("root_package"), platform.get("app_packages")
    if not root or not apps:
        raise ConfigError(
            "`root_package` e `app_packages` são obrigatórios em [tool.check-structure.platform]."
        )
    if not isinstance(apps, list) or not all(isinstance(app, str) and app for app in apps):
        raise ConfigError("`app_packages` deve ser uma lista de nomes de pacote.")
    return PlatformSettings(root_package=root, app_packages=tuple(apps))
