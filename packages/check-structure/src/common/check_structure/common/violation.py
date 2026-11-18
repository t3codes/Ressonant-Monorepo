from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    message: str
