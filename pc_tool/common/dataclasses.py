from dataclasses import dataclass

@dataclass
class Command:
    name: str
    id: int
    address: int
    data: bytes | None = None
    length: int | None = None