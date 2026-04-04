from test.common.asserts import assert_eq
from pc_tool.common.protocol import serialize_command_packet, calculate_crc16
from pc_tool.common.enums import *
from pc_tool.common.dataclasses import CommandPacket, Command

def mock_hal_roundtrip(packet: bytes) -> bytes:
    # Simulate a round trip through the HAL
    return packet

def test_command_serialization():
    # Create a command packet
    cmd = Command(
        name="READ_MEM",
        id=CommandId.READ_MEM,
        mem=MemType.RAM,
        address=0x20000000,
        length=16,
        data=None
    )

    pass