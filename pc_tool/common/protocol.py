from dataclasses import dataclass
from common.dataclasses import Command, CommandPacket, AckPacket

def calculate_crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
    return crc & 0xFF

def serialize_command_packet(command: Command) -> bytes:
    packet = CommandPacket(
        cmd_id=command.id,
        mem_id=command.mem,
        address=command.address,
        length=command.length,
        data=command.data
    )

    serialized = bytearray()
    serialized.append(packet.START_BYTE)
    serialized.append(packet.cmd_id)

    flags = 0
    if packet.mem_id is not None:
        flags |= 0x01
    if packet.length is not None:
        flags |= 0x02

    serialized.append(flags)

    if packet.mem_id is not None:
        serialized.append(packet.mem_id)
    
    serialized += packet.address.to_bytes(4, byteorder='little')

    if packet.length is not None:
        serialized += packet.length.to_bytes(2, byteorder='little')

    if packet.data is not None:
        serialized += packet.data
    
    crc_data = serialized[1:]  # Exclude START_BYTE for CRC calculation
    packet.crc = calculate_crc(crc_data)
    serialized.append(packet.crc)
    serialized.append(packet.END_BYTE)

    return bytes(serialized)

def deserialize_ack_packet(data: bytes) -> AckPacket:
    if len(data) < 5:
        raise ValueError("Data too short to be a valid AckPacket")

    if data[0] != AckPacket.START_BYTE or data[-1] != AckPacket.END_BYTE:
        raise ValueError("Invalid start or end byte in AckPacket")

    ack = AckPacket()
    ack.status = data[1]
    ack.cmd_id = data[2]
    ack.crc = data[-2]

    crc_data = data[1:-2]  # Exclude START_BYTE and END_BYTE for CRC calculation
    calculated_crc = calculate_crc(crc_data)

    if ack.crc != calculated_crc:
        raise ValueError("CRC mismatch in AckPacket")

    return ack