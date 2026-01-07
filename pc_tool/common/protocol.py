from dataclasses import dataclass
from common.dataclasses import Command, CommandPacket, AckPacket

def calculate_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001  # example CRC-16-IBM
            else:
                crc >>= 1
    return crc & 0xFFFF


def serialize_command_packet(command: Command) -> bytes:
    packet = CommandPacket(
        cmd_id=command.id,
        mem_id=command.mem,
        address=command.address,
        length=4,             # always 4 bytes
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
    serialized.append(flags)

    serialized.append(packet.mem_id if packet.mem_id is not None else 0x00)  # mem_id

    # address (4 bytes little endian)
    serialized += packet.address.to_bytes(4, byteorder="little")

    # length field (always 4)
    serialized += (4).to_bytes(2, byteorder="little")

    # data (4 bytes)
    serialized += packet.data

    # CRC16 over everything except START_BYTE
    crc_val = calculate_crc16(serialized[1:])
    serialized += crc_val.to_bytes(2, byteorder="little")

    # END_BYTE
    serialized.append(packet.END_BYTE)

    return bytes(serialized)
