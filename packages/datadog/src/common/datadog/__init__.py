"""Configuração lazy da instrumentação Datadog para aplicações do workspace."""

import os

_TRUE_VALUES = {"1", "true", "yes", "on"}


def initialize_datadog() -> bool:
    """Ativa instrumentação apenas com DD_TRACE_ENABLED explícito.

    O retorno é ``False`` sem importar ddtrace quando a flag está desligada, evitando
    inicialização de tracer, instrumentors ou workers de métricas na configuração padrão.
    """
    enabled = os.getenv("DD_TRACE_ENABLED", "false").strip().lower() in _TRUE_VALUES
    if not enabled:
        return False

    os.environ.setdefault("DD_LOGS_INJECTION", "true")
    os.environ.setdefault("DD_RUNTIME_METRICS_ENABLED", "true")

    from ddtrace import config, patch_all

    config.service = os.getenv("DD_SERVICE", "ressonant_backend")
    config.env = os.getenv("DD_ENV", os.getenv("ENVIRONMENT", "development"))
    version = os.getenv("DD_VERSION")
    if version:
        config.version = version
    patch_all()
    return True
