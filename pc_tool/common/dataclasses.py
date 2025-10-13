from dataclasses import dataclass

@dataclass
class Command:
    name: str
    id: int
    mem: int | None = None
    address: int = 0
    data: bytes | None = None
    length: int | None = None