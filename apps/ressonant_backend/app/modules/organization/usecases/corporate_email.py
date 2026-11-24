from __future__ import annotations

import re
import unicodedata

_CONNECTIVES = frozenset({"de", "da", "do", "dos", "das", "e"})
_SUFFIX_LIMIT = 1000


def normalize_name_tokens(full_name: str) -> list[str]:
    """Normaliza o nome conforme a regra fechada, sem derivar novos tokens."""
    folded = unicodedata.normalize("NFD", full_name.strip().lower())
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    return [token for token in re.findall(r"[a-z0-9]+", ascii_name) if token not in _CONNECTIVES]


def corporate_email_candidates(
    tokens: list[str], domain: str, *, suffix_limit: int = _SUFFIX_LIMIT
) -> list[str]:
    """Devolve as 5 tentativas da cascata, em ordem determinística.

    A tentativa 5 é expandida até `suffix_limit` homônimos adicionais.
    """
    normalized_domain = domain.strip().lower()
    if not tokens:
        raise ValueError("nome sem tokens validos para gerar o e-mail corporativo")
    if not normalized_domain or "@" in normalized_domain:
        raise ValueError("dominio corporativo invalido")

    first = tokens[0]
    last = tokens[-1]
    candidates = [f"{first}.{last}@{normalized_domain}"]

    if len(tokens) >= 3:
        second = tokens[1]
        penultimate = tokens[-2]
        candidates.extend(
            (
                f"{first}.{second}@{normalized_domain}",
                f"{first}.{second[0]}.{last}@{normalized_domain}",
                f"{first}.{penultimate}.{last}@{normalized_domain}",
            )
        )

    candidates.extend(
        f"{first}.{last}{number}@{normalized_domain}" for number in range(2, suffix_limit + 2)
    )
    return candidates
