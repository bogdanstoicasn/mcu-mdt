from enum import IntEnum,  StrEnum

MDT_PACKET_SIZE = 18
MDT_MAX_BREAKPOINTS = 4


class CommandId(IntEnum):
    READ_MEM = 0x01
    WRITE_MEM = 0x02
    READ_REG = 0x03
    WRITE_REG = 0x04
    PING = 0x05
    RESET = 0x06
    EXIT = 0x07
    HELP = 0x08
    CLEAR = 0x09
    BREAKPOINT = 0x0A

""" UTILITY ENUMS. These are used across the codebase for various purposes. """
class BreakpointControl(IntEnum):
    DISABLED = 0
    ENABLED = 1
    RESET = 2
    NEXT = 3

class MemType(IntEnum):
    RAM = 0
    FLASH = 1
    EEPROM = 2

class FenceType(IntEnum):
    START_BYTE = 0xAA
    END_BYTE = 0x55

""" PROTOCOL RELATED ENUMS. Check mcu_mdt_protocol.h for more details. """

class MDTOffset(IntEnum):
    START   = 0
    CMD_ID  = 1
    FLAGS   = 2
    SEQ     = 3
    MEM_ID  = 4
    ADDRESS = 5
    LENGTH  = 9
    DATA    = 11
    CRC     = 15
    END     = 17

class MDTFlags(IntEnum):
    MEM_ID_PRESENT   = 0x01  # Bit 0
    LENGTH_PRESENT   = 0x02  # Bit 1
    ACK_NACK         = 0x04  # Bit 2
    SEQ_PRESENT      = 0x08  # Bit 3
    LAST_PACKET      = 0x10  # Bit 4
    STATUS_ERROR     = 0x20  # Bit 5
    EVENT_PACKET     = 0x40  # Bit 6

""" END OF PROTOCOL RELATED ENUMS """

class MCUPlatforms(StrEnum):
    AVR = "avr"
    PIC = "pic"
    STM = "stm"

class UtilEnum(IntEnum):
    BAUDRATE_19200 = 19200
    WORD_SIZE = 4
    HALF_WORD_SIZE = 2
    COMMUNICATION_TIMEOUT = 5.0  # in seconds

class EventType(IntEnum):
    MDT_EVENT_TYPE_NONE = 0
    MDT_EVENT_BUFFER_OVERFLOW = 1
    MDT_EVENT_FAILED_PACKET = 2
    MDT_EVENT_BREAKPOINT_HIT = 3