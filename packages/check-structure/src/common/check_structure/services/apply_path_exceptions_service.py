from fnmatch import fnmatch

from common.check_structure.common.settings import PathException
from common.check_structure.common.violation import Violation


def apply_path_exceptions(
    violations: tuple[Violation, ...], exceptions: tuple[PathException, ...]
) -> tuple[Violation, ...]:
    return tuple(v for v in violations if not any(_covers(e, v) for e in exceptions))


def _covers(exception: PathException, violation: Violation) -> bool:
    if exception.rule != violation.rule:
        return False
    pattern = exception.path.rstrip("/")
    return fnmatch(violation.path, pattern) or fnmatch(violation.path, f"{pattern}/*")
