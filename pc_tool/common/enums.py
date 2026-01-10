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

class FenceType(IntEnum):
    START_BYTE = 0x7E
    END_BYTE = 0x7F

class UtilEnum(IntEnum):
    BAUDRATE_19200 = 19200
    WORD_SIZE = 4
    HALF_WORD_SIZE = 2
    COMMUNICATION_TIMEOUT = 5.0  # in seconds