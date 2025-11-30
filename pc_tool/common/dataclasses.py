from dataclasses import dataclass

@dataclass
class Command:
    name: str
    id: int
    mem: int | None = None
    address: int = 0
    data: bytes | None = None
    length: int | None = None

@dataclass
class CommandPacket:
    cmd_id: int = 0 # 1 byte
    flags: int = 0 # 1 byte
    mem_id: int | None = None # 1 byte
    address: int = 0 # 4 bytes
    length: int | None = None # 2 bytes (little endian)
    data: bytes | None = None # variable length
    crc: int | None = None # at serialization time

    START_BYTE: int = 0xAA
    END_BYTE: int = 0x55

@dataclass
class AckPacket:
    status: int = 0 # 1 byte
    cmd_id: int = 0 # 1 byte
    crc: int | None = None # at serialization time

    START_BYTE: int = 0xCC
    END_BYTE: int = 0x33