# common-datadog

Configuração compartilhada para instrumentação Datadog. `initialize_datadog()` só importa `ddtrace` e chama a instrumentação automática se `DD_TRACE_ENABLED` for `true`, `1`, `yes` ou `on`; sem essa flag não há tracer, patches nem runtime metrics iniciados.

Com a flag ativa, o pacote configura `DD_SERVICE`, `DD_ENV` e `DD_VERSION`, habilita correlação de logs e runtime metrics por padrão e aplica as integrações disponíveis do `ddtrace`. Configure o Agent via variáveis oficiais do ddtrace (`DD_AGENT_HOST`, `DD_TRACE_AGENT_PORT` ou `DD_TRACE_AGENT_URL`).

Os testes unitários validam o comportamento do feature flag sem contatar um Agent. A entrega de traces/logs/métricas em um Datadog Agent real depende de ambiente e credenciais externos e precisa ser validada nesse ambiente.
