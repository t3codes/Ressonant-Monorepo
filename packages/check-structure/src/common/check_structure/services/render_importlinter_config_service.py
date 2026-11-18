from collections import Counter

from common.check_structure.common.contract import Contract
from common.check_structure.common.settings import ExceptionEntry

SCALAR_OPTIONS = frozenset({"allow_indirect_imports"})


def render_importlinter_config(
    root_package: str,
    contracts: tuple[Contract, ...],
    exceptions: tuple[ExceptionEntry, ...] = (),
    include_external_packages: bool = False,
) -> str:
    lines = ["[importlinter]", f"root_packages = {_multiline((root_package,))}"]
    if include_external_packages:
        lines.append("include_external_packages = True")
    lines.append("")
    ignored = tuple(f"{e.source} -> {e.target}" for e in exceptions)
    for key, contract in zip(_section_keys(contracts), contracts, strict=True):
        lines.append(f"[importlinter:contract:{key}]")
        lines.append(f"name = {contract.name}")
        lines.append(f"type = {contract.kind}")
        for option, values in contract.options.items():
            lines.append(f"{option} = {_render_value(option, values)}")
        if ignored:
            lines.append(f"ignore_imports = {_multiline(ignored)}")
            lines.append("unmatched_ignore_imports_alerting = none")
        lines.append("")
    return "\n".join(lines)


def _section_keys(contracts: tuple[Contract, ...]) -> list[str]:
    totals = Counter(c.id for c in contracts)
    seen: Counter[str] = Counter()
    keys = []
    for contract in contracts:
        seen[contract.id] += 1
        unique = totals[contract.id] == 1
        keys.append(contract.id if unique else f"{contract.id}-{seen[contract.id]}")
    return keys


def _render_value(option: str, values: tuple[str, ...]) -> str:
    return values[0] if option in SCALAR_OPTIONS else _multiline(values)


def _multiline(values: tuple[str, ...]) -> str:
    return "".join(f"\n    {value}" for value in values)
