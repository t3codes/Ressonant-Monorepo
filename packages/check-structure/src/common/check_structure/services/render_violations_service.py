from itertools import groupby

from common.check_structure.common.violation import Violation


def render_violations(violations: tuple[Violation, ...]) -> str:
    if not violations:
        return "Arquivos e pastas: nenhuma violação."
    lines = ["Arquivos e pastas", "----------------"]
    ordered = sorted(violations, key=lambda v: (v.rule, v.path))
    for rule, group in groupby(ordered, key=lambda v: v.rule):
        items = list(group)
        lines.append(f"\n{rule} ({len(items)})")
        lines.extend(f"-   {v.path}: {v.message}" for v in items)
    lines.append(f"\nArquivos e pastas: {len(violations)} violações.")
    return "\n".join(lines)
