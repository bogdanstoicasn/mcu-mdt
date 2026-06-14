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
    "RAM": 0, "FLASH": 1, "EEPROM": 2, "ERASE": 3,
    "DISABLED": 0, "ENABLED": 1, "RESET": 2, "NEXT": 3, "MASK": 3,
}

MCU_METADATA_FLASH = {
    "memories": {
        "IRAM":   {"type": "ram",   "start": 0x20000000, "size": 0x5000},
        "IFLASH": {"type": "flash", "start": 0x08000000, "size": 0x10000},
    },
    "modules": {},
    # Simulates a firmware that occupies the first 0x3000 bytes of flash.
    # Pages 0x08000000–0x08002FFF are protected; free space starts at 0x08003000.
    "firmware": {
        "start":     0x08000000,
        "end":       0x08003000,
        "size":      0x3000,
        "page_size": 0x400,      # 1 KB pages (F030 low/medium density)
    },
}

# AVR-like metadata: mirrors what _ATDFLoader produces from a real ATDF.
# Key differences from STM32:
#   - No <instance> elements - no "instances" list - base address is 0
#   - Register "offset" is the ABSOLUTE address in the AVR I/O address space
#   - Register "size" is in BYTES (not bits): 1 = 8-bit, 2 = 16-bit
#   - Register names never contain underscores (verified across all ATmega ATDFs)
# Values match the real ATmega48 ATDF (USART0 and TWI peripherals).
MCU_METADATA_AVR = {
    "memories": {
        "IRAM": {"type": "ram", "start": 0x0100, "size": 0x0200},
    },
    "modules": {
        "USART": {
            "caption": "USART",
            "instances": [],           # ATmega ATDF has no instance offsets here
            "register_groups": {
                "USART0": {
                    "offset": "0x00",  # base is 0; register offsets are absolute
                    "registers": {
                        "UDR0":   {"offset": "0xC6", "size": "1", "rw": "read-write"},
                        "UCSR0A": {"offset": "0xC0", "size": "1", "rw": "read-write"},
                        "UCSR0B": {"offset": "0xC1", "size": "1", "rw": "read-write"},
                        "UCSR0C": {"offset": "0xC2", "size": "1", "rw": "read-write"},
                        "UBRR0":  {"offset": "0xC4", "size": "2", "rw": "read-write"},
                    },
                },
            },
        },
        "TWI": {
            "caption": "Two Wire Serial Interface",
            "instances": [],
            "register_groups": {
                "TWI": {
                    "offset": "0x00",
                    "registers": {
                        "TWBR": {"offset": "0xB8", "size": "1", "rw": "read-write"},
                        "TWSR": {"offset": "0xB9", "size": "1", "rw": "read-write"},
                        "TWDR": {"offset": "0xBB", "size": "1", "rw": "read-write"},
                        "TWCR": {"offset": "0xBC", "size": "1", "rw": "read-write"},
                    },
                },
            },
        },
    },
}

def _meta_ram(start=0x20000000, size=0x5000):
    return {
        "memories": {
            "IRAM": {"type": "ram", "start": start, "size": size}
        },
        "modules": {}
    }

def _meta_flash(start=0x08000000, size=0x20000):
    return {
        "memories": {
            "FLASH": {"type": "flash", "start": start, "size": size}
        },
        "modules": {}
    }

def _meta_eeprom(start=0x810000, size=0x400):
    return {
        "memories": {
            "EEPROM": {"type": "eeprom", "start": start, "size": size}
        },
        "modules": {}
    }

def _meta_all():
    return {
        "memories": {
            "IRAM":   {"type": "ram",    "start": 0x20000000, "size": 0x5000},
            "FLASH":  {"type": "flash",  "start": 0x08000000, "size": 0x20000},
            "EEPROM": {"type": "eeprom", "start": 0x810000,   "size": 0x400},
        },
        "modules": {}
    }

def _reg_meta(base=0x40013800, reg_offset=0x00, reg_size_bits=32, rw="read-write"):
    return {
        "memories": {},
        "modules": {
            "USART1": {
                "instances": [
                    {"register_group": "USART1", "offset": base}
                ],
                "register_groups": {
                    "USART1": {
                        "offset": base,
                        "registers": {
                            "SR": {
                                "offset": reg_offset,
                                "size": reg_size_bits,
                                "rw": rw,
                            },
                            "DR": {
                                "offset": reg_offset + 0x04,
                                "size": reg_size_bits,
                                "rw": rw,
                            },
                            "BRR": {
                                "offset": reg_offset + 0x08,
                                "size": reg_size_bits,
                                "rw": rw,
                            },
                        }
                    }
                }
            }
        }
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