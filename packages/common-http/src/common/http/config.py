from dataclasses import dataclass


@dataclass(frozen=True)
class HttpClientConfig:
    """Política de um client HTTP. Todos os tempos são em segundos.

    Os campos não informados assumem o default. `keepalive_expiry` deve ficar abaixo
    do idle timeout do servidor destino (uvicorn fecha conexões ociosas após 5s),
    por isso o default de 3s.
    """

    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    pool_timeout: float = 5.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 3.0
