from test.common.asserts import assert_eq
from pc_tool.common.dataclasses import Command, CommandPacket
from pc_tool.common.enums import (
    MDT_PACKET_SIZE, MDTOffset, MDTFlags, CommandId, MemType,
    BreakpointControl, WatchpointControl
)
from pc_tool.common.protocol import (
    serialize_command_packet,
    deserialize_command_packet,
    validate_command_packet,
    is_nack_packet,
    calculate_crc16,
)


# Helpers
def _make_ping() -> Command:
    return Command(name="PING", id=CommandId.PING, mem=None, address=0, data=None, length=0)

def _make_read_mem(address: int = 0x20000000, length: int = 4) -> Command:
    return Command(name="READ_MEM", id=CommandId.READ_MEM, mem=MemType.RAM,
                   address=address, data=None, length=length)

def _make_write_mem(address: int = 0x20000000, data: bytes = b'\x01\x02\x03\x04') -> Command:
    return Command(name="WRITE_MEM", id=CommandId.WRITE_MEM, mem=MemType.RAM,
                   address=address, data=data, length=len(data))

def _serialize(cmd: Command, seq: int = 0) -> bytes:
    return serialize_command_packet(cmd, seq=seq, multi=False, last=False)



# Serialize
def test_serialize_packet_size():
    pkt = _serialize(_make_ping())
    assert_eq(len(pkt), MDT_PACKET_SIZE)

def test_serialize_start_end_bytes():
    pkt = _serialize(_make_ping())
    assert_eq(pkt[MDTOffset.START], 0xAA)
    assert_eq(pkt[MDTOffset.END],   0x55)

def test_serialize_cmd_id():
    pkt = _serialize(_make_ping())
    assert_eq(pkt[MDTOffset.CMD_ID], CommandId.PING)

def test_serialize_address_little_endian():
    cmd = _make_read_mem(address=0x20000100)
    pkt = _serialize(cmd)
    addr = int.from_bytes(pkt[MDTOffset.ADDRESS:MDTOffset.ADDRESS + 4], byteorder="little")
    assert_eq(addr, 0x20000100)

def test_serialize_length_field():
    cmd = _make_read_mem(length=4)
    pkt = _serialize(cmd)
    length = int.from_bytes(pkt[MDTOffset.LENGTH:MDTOffset.LENGTH + 2], byteorder="little")
    assert_eq(length, 4)

def test_serialize_data_field():
    data = b'\xDE\xAD\xBE\xEF'
    cmd = _make_write_mem(data=data)
    pkt = _serialize(cmd)
    assert_eq(pkt[MDTOffset.DATA:MDTOffset.DATA + 4], data)

def test_serialize_mem_id_present_flag():
    cmd = _make_read_mem()
    pkt = _serialize(cmd)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.MEM_ID_PRESENT), True)

def test_serialize_mem_id_absent_for_ping():
    pkt = _serialize(_make_ping())
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.MEM_ID_PRESENT), False)

def test_serialize_seq_field():
    pkt = serialize_command_packet(_make_ping(), seq=7, multi=True, last=False)
    assert_eq(pkt[MDTOffset.SEQ], 7)

def test_serialize_multi_flag():
    pkt = serialize_command_packet(_make_ping(), seq=0, multi=True, last=False)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.SEQ_PRESENT), True)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.LAST_PACKET), False)

def test_serialize_last_flag():
    pkt = serialize_command_packet(_make_ping(), seq=0, multi=True, last=True)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.LAST_PACKET), True)

def test_serialize_crc_correct():
    pkt = _serialize(_make_ping())
    crc_received = int.from_bytes(pkt[MDTOffset.CRC:MDTOffset.CRC + 2], byteorder="little")
    crc_calc     = calculate_crc16(pkt[MDTOffset.CMD_ID:MDTOffset.CRC])
    assert_eq(crc_received, crc_calc)



# Deserialize
def test_deserialize_roundtrip_ping():
    cmd = _make_ping()
    pkt = _serialize(cmd)
    result = deserialize_command_packet(pkt)
    assert_eq(result.cmd_id, CommandId.PING)
    assert_eq(result.address, 0)

def test_deserialize_roundtrip_read_mem():
    cmd = _make_read_mem(address=0x20000200, length=4)
    pkt = _serialize(cmd)
    result = deserialize_command_packet(pkt)
    assert_eq(result.cmd_id, CommandId.READ_MEM)
    assert_eq(result.address, 0x20000200)
    assert_eq(result.length,  4)

def test_deserialize_roundtrip_write_mem():
    data = b'\x11\x22\x33\x44'
    cmd  = _make_write_mem(data=data)
    pkt  = _serialize(cmd)
    result = deserialize_command_packet(pkt)
    assert_eq(result.cmd_id, CommandId.WRITE_MEM)
    assert_eq(result.data,   data)

def test_deserialize_raises_on_wrong_length():
    pkt = _serialize(_make_ping())
    raised = False
    try:
        deserialize_command_packet(pkt[:-1])  # truncate one byte
    except ValueError:
        raised = True
    assert_eq(raised, True)

def test_deserialize_raises_on_bad_start_byte():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.START] = 0x00
    raised = False
    try:
        deserialize_command_packet(bytes(pkt))
    except ValueError:
        raised = True
    assert_eq(raised, True)

def test_deserialize_raises_on_bad_end_byte():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.END] = 0x00
    raised = False
    try:
        deserialize_command_packet(bytes(pkt))
    except ValueError:
        raised = True
    assert_eq(raised, True)

def test_deserialize_raises_on_crc_mismatch():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.DATA] ^= 0xFF  # corrupt data field
    raised = False
    try:
        deserialize_command_packet(bytes(pkt))
    except ValueError:
        raised = True
    assert_eq(raised, True)


# Validate command packets
def test_validate_valid_packet():
    pkt = _serialize(_make_ping())
    assert_eq(validate_command_packet(pkt), True)

def test_validate_wrong_length():
    pkt = _serialize(_make_ping())
    assert_eq(validate_command_packet(pkt[:-1]), False)

def test_validate_bad_start_byte():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.START] = 0x00
    assert_eq(validate_command_packet(bytes(pkt)), False)

def test_validate_bad_end_byte():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.END] = 0x00
    assert_eq(validate_command_packet(bytes(pkt)), False)

def test_validate_bad_crc():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.CRC] ^= 0xFF
    assert_eq(validate_command_packet(bytes(pkt)), False)

def test_validate_status_error_flag_fails():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.FLAGS] |= MDTFlags.STATUS_ERROR
    # recalculate CRC so only flag difference is tested
    crc = calculate_crc16(bytes(pkt[MDTOffset.CMD_ID:MDTOffset.CRC]))
    pkt[MDTOffset.CRC]     = crc & 0xFF
    pkt[MDTOffset.CRC + 1] = (crc >> 8) & 0xFF
    assert_eq(validate_command_packet(bytes(pkt)), False)


# NACK packet detection
def test_is_nack_true():
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x00
    pkt[MDTOffset.FLAGS]  = MDTFlags.ACK_NACK | MDTFlags.STATUS_ERROR
    pkt[MDTOffset.END]    = 0x55
    assert_eq(is_nack_packet(bytes(pkt)), True)

def test_is_nack_false_for_normal_ack():
    pkt = bytearray(_serialize(_make_ping()))
    pkt[MDTOffset.FLAGS] |= MDTFlags.ACK_NACK  # ACK but no STATUS_ERROR
    assert_eq(is_nack_packet(bytes(pkt)), False)

def test_is_nack_false_for_nonzero_cmd_id():
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x05  # PING cmd_id — not a NACK
    pkt[MDTOffset.FLAGS]  = MDTFlags.ACK_NACK | MDTFlags.STATUS_ERROR
    pkt[MDTOffset.END]    = 0x55
    assert_eq(is_nack_packet(bytes(pkt)), False)

def test_is_nack_false_for_wrong_length():
    pkt = bytearray(MDT_PACKET_SIZE - 1)
    assert_eq(is_nack_packet(bytes(pkt)), False)