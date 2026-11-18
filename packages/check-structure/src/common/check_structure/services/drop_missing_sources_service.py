from dataclasses import replace

from common.check_structure.common.contract import Contract

SOURCES = "source_modules"


def literal_sources(contracts: tuple[Contract, ...]) -> tuple[str, ...]:
    return tuple(sorted({s for c in contracts for s in c.options[SOURCES] if "*" not in s}))


def drop_missing_sources(
    contracts: tuple[Contract, ...], missing: frozenset[str]
) -> tuple[tuple[Contract, ...], tuple[str, ...]]:
    """O import-linter aborta todos os contratos se uma origem não existe. Remove essas
    origens (e o contrato que ficar sem nenhuma) e devolve um aviso para cada uma."""
    kept = []
    warnings = []
    for contract in contracts:
        sources = contract.options[SOURCES]
        remaining = tuple(s for s in sources if s not in missing)
        warnings += [
            f"`{contract.name}` não verifica `{s}`: o módulo não existe"
            for s in sources
            if s in missing
        ]
        if remaining:
            kept.append(replace(contract, options={**contract.options, SOURCES: remaining}))
    return tuple(kept), tuple(warnings)
