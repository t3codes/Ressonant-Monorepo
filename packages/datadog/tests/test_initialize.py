import sys
from types import ModuleType, SimpleNamespace

from common.datadog import initialize_datadog


def test_disabled_does_not_import_ddtrace(monkeypatch) -> None:
    monkeypatch.delenv("DD_TRACE_ENABLED", raising=False)
    sys.modules.pop("ddtrace", None)

    assert initialize_datadog() is False
    assert "ddtrace" not in sys.modules


def test_enabled_sets_service_and_instrumentation_options(monkeypatch) -> None:
    calls: list[bool] = []
    fake = ModuleType("ddtrace")
    fake.config = SimpleNamespace(service=None, env=None, version=None)
    fake.patch_all = lambda: calls.append(True)
    monkeypatch.setitem(sys.modules, "ddtrace", fake)
    monkeypatch.setenv("DD_TRACE_ENABLED", "true")
    monkeypatch.setenv("DD_SERVICE", "test-api")
    monkeypatch.setenv("DD_ENV", "test")
    monkeypatch.setenv("DD_VERSION", "test-version")

    assert initialize_datadog() is True
    assert fake.config.service == "test-api"
    assert fake.config.env == "test"
    assert fake.config.version == "test-version"
    assert calls == [True]
    assert __import__("os").environ["DD_LOGS_INJECTION"] == "true"
    assert __import__("os").environ["DD_RUNTIME_METRICS_ENABLED"] == "true"
