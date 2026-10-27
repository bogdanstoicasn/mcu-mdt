"""The MDT wire format, as src/mcu_mdt_protocol.h defines it.

Every packet is 18 bytes:

    START | CMD_ID | FLAGS | SEQ | MEM_ID | ADDRESS (4) | LENGTH (2) | DATA (4) | CRC (2) | END

Multi-byte fields are little-endian. The CRC (CRC-CCITT, poly 0x1021, init 0xFFFF) covers CMD_ID
through DATA. test/unit/test_wire_contract.py checks these values against the C headers.
"""

from dataclasses import dataclass
from enum import IntEnum, IntFlag

from pc_tool import MdtError

PACKET_SIZE = 18
START_BYTE = 0xAA
END_BYTE = 0x55
WORD_SIZE = 4                     # bytes in the DATA field: the most one packet carries


class Offset(IntEnum):
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


class Flag(IntFlag):
    MEM_ID_PRESENT = 0x01
    LENGTH_PRESENT = 0x02
    ACK_NACK       = 0x04
    SEQ_PRESENT    = 0x08
    LAST_PACKET    = 0x10
    STATUS_ERROR   = 0x20
    EVENT_PACKET   = 0x40


class CommandId(IntEnum):
    READ_MEM   = 0x01
    WRITE_MEM  = 0x02
    READ_REG   = 0x03
    WRITE_REG  = 0x04
    PING       = 0x05
    RESET      = 0x06
    BREAKPOINT = 0x07
    WATCHPOINT = 0x08
    EXIT       = 0x09             # EXIT, HELP, CLEAR never leave the PC
    HELP       = 0x0A
    CLEAR      = 0x0B


class MemType(IntEnum):           # MEM_ID of READ_MEM / WRITE_MEM
    RAM    = 0
    FLASH  = 1
    EEPROM = 2
    ERASE  = 3                    # erase the flash page holding ADDRESS


class BreakpointControl(IntEnum):  # MEM_ID of BREAKPOINT
    DISABLED = 0
    ENABLED  = 1
    RESET    = 2
    NEXT     = 3


class WatchpointControl(IntEnum):  # MEM_ID of WATCHPOINT
    DISABLED = 0
    ENABLED  = 1
    RESET    = 2
    MASK     = 3


class EventType(IntEnum):          # MEM_ID of an event packet
    INTERNAL_MDT_EVENT_TYPE_NONE       = 0
    INTERNAL_MDT_EVENT_BUFFER_OVERFLOW = 1
    INTERNAL_MDT_EVENT_FAILED_PACKET   = 2
    INTERNAL_MDT_EVENT_BREAKPOINT_HIT  = 3
    INTERNAL_MDT_EVENT_WATCHPOINT_HIT  = 4


class PacketError(MdtError):
    """A received packet that is not a valid MDT packet (size, fences or CRC)."""


@dataclass
class Command:
    """One request as the user gave it. Commands longer than a word are split by the client."""
    name: str
    id: int
    mem: int | None = None          # memory zone or breakpoint/watchpoint control
    address: int = 0                # address or breakpoint/watchpoint slot
    data: bytes | None = None
    length: int | None = None


@dataclass
class Packet:
    """One decoded packet."""
    cmd_id: int
    flags: int
    seq: int
    mem_id: int | None              # None when MEM_ID_PRESENT is clear
    address: int
    length: int
    data: bytes
    crc: int

    @property
    def is_ack(self) -> bool:
        return bool(self.flags & Flag.ACK_NACK)

    @property
    def is_error(self) -> bool:
        return bool(self.flags & Flag.STATUS_ERROR)

    @property
    def is_event(self) -> bool:
        return bool(self.flags & Flag.EVENT_PACKET)


def crc16(data: bytes) -> int:
    """CRC-CCITT (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        x = ((crc >> 8) ^ byte) & 0xFF
        x ^= x >> 4
        crc = ((crc << 8) ^ (x << 12) ^ (x << 5) ^ x) & 0xFFFF
    return crc


def encode(command: Command, seq: int = 0, multi: bool = False, last: bool = False) -> bytes:
    """One packet for *command*. Its data must be exactly one word; the length is capped at one."""
    data = command.data if command.data is not None else bytes(WORD_SIZE)
    if len(data) != WORD_SIZE:
        raise PacketError(f"Data must be exactly {WORD_SIZE} bytes.")
    length = min(command.length or 0, WORD_SIZE)

    flags = Flag.LENGTH_PRESENT
    if command.mem is not None:
        flags |= Flag.MEM_ID_PRESENT
    if multi:
        flags |= Flag.SEQ_PRESENT
        if last:
            flags |= Flag.LAST_PACKET

    body = (bytes([command.id, flags, seq, command.mem or 0])
            + command.address.to_bytes(4, "little")
            + length.to_bytes(2, "little")
            + data)
    return bytes([START_BYTE]) + body + crc16(body).to_bytes(2, "little") + bytes([END_BYTE])


def decode(raw: bytes) -> Packet:
    """Check the size, fences and CRC of *raw* and decode it; raise PacketError if any is wrong."""
    if len(raw) != PACKET_SIZE:
        raise PacketError(f"Invalid packet length: {len(raw)}, expected {PACKET_SIZE}.")
    if raw[Offset.START] != START_BYTE:
        raise PacketError(f"Bad start byte: 0x{raw[Offset.START]:02X}.")
    if raw[Offset.END] != END_BYTE:
        raise PacketError(f"Bad end byte: 0x{raw[Offset.END]:02X}.")
    received = int.from_bytes(raw[Offset.CRC:Offset.CRC + 2], "little")
    calculated = crc16(raw[Offset.CMD_ID:Offset.CRC])
    if received != calculated:
        raise PacketError(f"CRC mismatch: received 0x{received:04X}, calculated 0x{calculated:04X}.")

    flags = raw[Offset.FLAGS]
    return Packet(
        cmd_id=raw[Offset.CMD_ID],
        flags=flags,
        seq=raw[Offset.SEQ],
        mem_id=raw[Offset.MEM_ID] if flags & Flag.MEM_ID_PRESENT else None,
        address=int.from_bytes(raw[Offset.ADDRESS:Offset.ADDRESS + 4], "little"),
        length=int.from_bytes(raw[Offset.LENGTH:Offset.LENGTH + 2], "little"),
        data=raw[Offset.DATA:Offset.DATA + WORD_SIZE],
        crc=received,
    )


def is_nack(raw: bytes) -> bool:
    """A NACK: the MCU rejected a malformed packet (CMD_ID 0, ACK and ERROR set). The CRC is not checked."""
    return (len(raw) == PACKET_SIZE and raw[Offset.CMD_ID] == 0
            and raw[Offset.FLAGS] & (Flag.ACK_NACK | Flag.STATUS_ERROR) == Flag.ACK_NACK | Flag.STATUS_ERROR)
