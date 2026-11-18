from dataclasses import dataclass


@dataclass(frozen=True)
class Contract:
    id: str
    name: str
    kind: str
    options: dict[str, tuple[str, ...]]
