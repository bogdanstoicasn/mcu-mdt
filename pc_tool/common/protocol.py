from dataclasses import dataclass
from common.dataclasses import Command

@dataclass
class CommProtocol:
    pass

def encode_packet(cmd: Command) -> bytes:
    payload = bytearray()

    payload += cmd.address.to_bytes(2, 'little')
    if cmd.length is not None:
        payload += cmd.length.to_bytes(1, 'little')
    if cmd.data is not None:
        payload += cmd.data

    length = len(payload)
    packet = bytearray([0xAA, cmd.id, length]) + payload

    crc = 0
    for b in packet[1:]:  # exclude SOF
        crc ^= b  # simple XOR checksum
    packet.append(crc)

    return bytes(packet)

