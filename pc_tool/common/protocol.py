from dataclasses import dataclass
from common.dataclasses import Command, CommandPacket
from common.enums import MDT_PACKET_SIZE, MDTOffset

def calculate_crc16(data: bytes) -> int:
    crc = 0xFFFF

    for b in data:
        x = ((crc >> 8) ^ b) & 0xFF
        x ^= (x >> 4)
        crc = (
            ((crc << 8) & 0xFFFF) ^
            ((x << 12) & 0xFFFF) ^
            ((x << 5) & 0xFFFF) ^
            x
        )

    return crc & 0xFFFF


def serialize_command_packet(command: Command, seq: int, multi: bool, last: bool) -> bytes:
    packet = CommandPacket(
        cmd_id=command.id,
        seq=seq,
        mem_id=command.mem,
        address=command.address,
        length=min(command.length if command.length is not None else 0, 4),  # Ensure length does not exceed 4
        data=command.data if command.data is not None else b'\x00\x00\x00\x00'
    )

    if len(packet.data) != 4:
        raise ValueError("Data length must be exactly 4 bytes for serialization.")

    serialized = bytearray()
    serialized.append(packet.START_BYTE)       # START_BYTE
    serialized.append(packet.cmd_id)           # cmd_id

    # flags
    flags = 0
    if packet.mem_id is not None:
        flags |= 0x01  # mem_id present
    flags |= 0x02      # length always present

    if multi:
        flags |= 0x08  # sequence number present
        if last:
            flags |= 0x10  # last packet in sequence

    serialized.append(flags)

    serialized.append(packet.seq)              # seq

    serialized.append(packet.mem_id if packet.mem_id is not None else 0x00)  # mem_id

    # address (4 bytes little endian)
    serialized += packet.address.to_bytes(4, byteorder="little")

    # length field (always 4)
    serialized += packet.length.to_bytes(2, byteorder="little")

    # data (4 bytes)
    serialized += packet.data

    # CRC16 over everything except START_BYTE
    crc_val = calculate_crc16(serialized[1:])
    serialized += crc_val.to_bytes(2, byteorder="little")

    # END_BYTE
    serialized.append(packet.END_BYTE)

    return bytes(serialized)

def validate_command_packet(packet: bytes) -> bool:
    """Validate an MDT packet received from the MCU."""
    if len(packet) != MDT_PACKET_SIZE:
        print(f"Invalid packet length: {len(packet)}. Expected: {MDT_PACKET_SIZE}")
        return False

    if packet[MDTOffset.START] != CommandPacket.START_BYTE:
        print(f"Invalid start byte: {packet[MDTOffset.START]:02X}. Expected: {CommandPacket.START_BYTE:02X}")
        return False

    if packet[MDTOffset.END] != CommandPacket.END_BYTE:
        print(f"Invalid end byte: {packet[MDTOffset.END]:02X}. Expected: {CommandPacket.END_BYTE:02X}")
        return False

    # Validate CRC16
    crc_received = int.from_bytes(packet[MDTOffset.CRC : MDTOffset.CRC + 2], byteorder="little")
    crc_calculated = calculate_crc16(packet[MDTOffset.CMD_ID : MDTOffset.CRC])

    if crc_received != crc_calculated:
        print(f"CRC mismatch: received {crc_received:04X}, calculated {crc_calculated:04X}")
        return False

    # Check if the command error/status bit is set (5th bit of flags)
    flags = packet[MDTOffset.FLAGS]
    if flags & 0x20:  # MDT_FLAG_ERROR / custom status bit
        print("Command execution error indicated by status flag.")
        return False

    return True
