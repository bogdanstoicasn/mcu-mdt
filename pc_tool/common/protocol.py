from pc_tool.common.dataclasses import Command, CommandPacket
from pc_tool.common.enums import MDT_PACKET_SIZE, MDTOffset, MDTFlags, UtilEnum
from pc_tool.common.logger import MDTLogger

_LE = "little"  # all multi-byte fields are little-endian


def calculate_crc16(data: bytes) -> int:
    """CRC-CCITT (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for b in data:
        x = ((crc >> 8) ^ b) & 0xFF
        x ^= x >> 4
        crc = (
            ((crc << 8) & 0xFFFF) ^
            ((x << 12) & 0xFFFF) ^
            ((x  << 5) & 0xFFFF) ^
            x
        )
    return crc & 0xFFFF

def _crc_of(packet: bytes) -> int:
    """Compute the CRC over the packet payload (CMD_ID through end of DATA)."""
    return calculate_crc16(packet[MDTOffset.CMD_ID : MDTOffset.CRC])


def _crc_from(packet: bytes) -> int:
    """Extract the CRC stored in the packet."""
    return int.from_bytes(packet[MDTOffset.CRC : MDTOffset.CRC + 2], _LE)


def serialize_command_packet(command: Command, seq: int, multi: bool, last: bool) -> bytes:
    data   = command.data if command.data is not None else b'\x00\x00\x00\x00'
    length = min(command.length if command.length is not None else 0, UtilEnum.WORD_SIZE)

    if len(data) != UtilEnum.WORD_SIZE:
        raise ValueError("Data must be exactly 4 bytes.")

    # Flags
    flags = MDTFlags.LENGTH_PRESENT
    if command.mem is not None:
        flags |= MDTFlags.MEM_ID_PRESENT
    if multi:
        flags |= MDTFlags.SEQ_PRESENT
        if last:
            flags |= MDTFlags.LAST_PACKET

    buf = bytearray()
    buf.append(CommandPacket.START_BYTE)
    buf.append(command.id)
    buf.append(flags)
    buf.append(seq)
    buf.append(command.mem if command.mem is not None else 0x00)
    buf += command.address.to_bytes(UtilEnum.WORD_SIZE, _LE)
    buf += length.to_bytes(UtilEnum.HALF_WORD_SIZE,  _LE)
    buf += data
    buf += calculate_crc16(buf[1:]).to_bytes(UtilEnum.HALF_WORD_SIZE, _LE)
    buf.append(CommandPacket.END_BYTE)

    return bytes(buf)


def deserialize_command_packet(packet: bytes) -> CommandPacket:
    if len(packet) != MDT_PACKET_SIZE:
        raise ValueError(f"Invalid packet length: {len(packet)}, expected {MDT_PACKET_SIZE}.")

    if packet[MDTOffset.START] != CommandPacket.START_BYTE:
        raise ValueError(f"Bad start byte: 0x{packet[MDTOffset.START]:02X}.")

    if packet[MDTOffset.END] != CommandPacket.END_BYTE:
        raise ValueError(f"Bad end byte: 0x{packet[MDTOffset.END]:02X}.")

    if _crc_from(packet) != _crc_of(packet):
        raise ValueError(
            f"CRC mismatch: received 0x{_crc_from(packet):04X}, "
            f"calculated 0x{_crc_of(packet):04X}."
        )

    flags  = packet[MDTOffset.FLAGS]
    mem_id = packet[MDTOffset.MEM_ID] if (flags & MDTFlags.MEM_ID_PRESENT) else None

    return CommandPacket(
        cmd_id  = packet[MDTOffset.CMD_ID],
        flags   = flags,
        seq     = packet[MDTOffset.SEQ],
        mem_id  = mem_id,
        address = int.from_bytes(packet[MDTOffset.ADDRESS : MDTOffset.ADDRESS + UtilEnum.WORD_SIZE],     _LE),
        length  = int.from_bytes(packet[MDTOffset.LENGTH  : MDTOffset.LENGTH  + UtilEnum.HALF_WORD_SIZE], _LE),
        data    = packet[MDTOffset.DATA : MDTOffset.DATA + UtilEnum.WORD_SIZE],
        crc     = _crc_from(packet),
    )


def is_nack_packet(packet: bytes) -> bool:
    """Return True if the packet is a NACK (ACK+ERROR flags set, cmd_id == 0)."""
    if len(packet) != MDT_PACKET_SIZE:
        MDTLogger.error(f"Invalid packet length: {len(packet)}, expected {MDT_PACKET_SIZE}.", code=3)
        return False

    flags = packet[MDTOffset.FLAGS]
    return (
        packet[MDTOffset.CMD_ID] == 0
        and bool(flags & MDTFlags.ACK_NACK)
        and bool(flags & MDTFlags.STATUS_ERROR)
    )


def validate_command_packet(packet: bytes) -> bool:
    """Validate framing, CRC, and status flag of a packet received from the MCU."""
    if len(packet) != MDT_PACKET_SIZE:
        MDTLogger.error(f"Invalid packet length: {len(packet)}, expected {MDT_PACKET_SIZE}.", code=3)
        return False

    if packet[MDTOffset.START] != CommandPacket.START_BYTE:
        MDTLogger.error(f"Bad start byte: 0x{packet[MDTOffset.START]:02X}.", code=3)
        return False

    if packet[MDTOffset.END] != CommandPacket.END_BYTE:
        MDTLogger.error(f"Bad end byte: 0x{packet[MDTOffset.END]:02X}.", code=3)
        return False

    if _crc_from(packet) != _crc_of(packet):
        MDTLogger.error(
            f"CRC mismatch: received 0x{_crc_from(packet):04X}, "
            f"calculated 0x{_crc_of(packet):04X}.",
            code=3,
        )
        return False

    if packet[MDTOffset.FLAGS] & MDTFlags.STATUS_ERROR:
        MDTLogger.error("Command execution error indicated by status flag.", code=3)
        return False

    return True
