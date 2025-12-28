from enum import IntEnum

class CommandId(IntEnum):
    READ_MEM = 0x01
    WRITE_MEM = 0x02
    READ_REG = 0x03
    WRITE_REG = 0x04
    PING = 0x05
    RESET = 0x06
    EXIT = 0x07
    HELP = 0x08

class MemType(IntEnum):
    RAM = 0
    FLASH = 1
    EEPROM = 2