# Fixtures
from pc_tool.common.enums import MDT_PACKET_SIZE


COMMANDS = {
    "PING":       {"id": 0x05, "params": []},
    "RESET":      {"id": 0x06, "params": []},
    "READ_MEM": {
        "id": 0x01,
        "params": [
            {"name": "control_value", "type": "str"},
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "len",           "type": "uint32", "format": "dec"},
        ],
    },
    "WRITE_MEM": {
        "id": 0x02,
        "params": [
            {"name": "control_value", "type": "str"},
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "len",           "type": "uint32", "format": "dec"},
            {"name": "data",          "type": "bytes"},
        ],
    },
    "READ_REG": {
        "id": 0x03,
        "params": [{"name": "address", "type": "uint32_or_str", "format": "hex"}],
    },
    "WRITE_REG": {
        "id": 0x04,
        "params": [
            {"name": "address", "type": "uint32_or_str", "format": "hex"},
            {"name": "data",    "type": "bytes"},
        ],
    },
    "BREAKPOINT": {
        "id": 0x07,
        "params": [
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "control_value", "type": "str"},
        ],
    },
    "WATCHPOINT": {
        "id": 0x08,
        "params": [
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "control_value", "type": "str"},
            {"name": "wp_data",       "type": "uint32", "format": "hex"},
        ],
    },
}

CONTROL_VALUES = {
    "RAM": 0, "FLASH": 1, "EEPROM": 2,
    "DISABLED": 0, "ENABLED": 1, "RESET": 2, "NEXT": 3, "MASK": 3,
}

MCU_METADATA_RAM = {
    "memories": {
        "IRAM": {"type": "ram", "start": 0x20000000, "size": 0x5000},
    },
    "modules": {},
}

MCU_METADATA_REG = {
    "memories": {},
    "modules": {
        "USART1": {
            "instances": [{"register_group": "USART1", "offset": 0x40013800}],
            "register_groups": {
                "USART1": {
                    "offset": 0x40013800,
                    "registers": {
                        "SR":  {"offset": 0x00, "size": 32, "rw": "read-write"},
                        "DR":  {"offset": 0x04, "size": 32, "rw": "read-write"},
                        "BRR": {"offset": 0x08, "size": 32, "rw": "read-write"},
                    },
                }
            },
        }
    },
}


# Mock infrastructure
class MockUART:
    """Perfect byte-level loopback, bytes written are instantly readable."""

    def __init__(self):
        self._buf = bytearray()

    def write(self, data: bytes):
        self._buf.extend(data)

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:n])
        self._buf = self._buf[n:]
        return chunk

    def read_packet(self) -> bytes:
        return self.read(MDT_PACKET_SIZE)

    @property
    def pending(self) -> int:
        return len(self._buf)