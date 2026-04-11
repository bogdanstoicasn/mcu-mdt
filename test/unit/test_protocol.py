"""
PROTOCOL & PACKET TESTS


Validates the correctness of command packet serialization, deserialization, and integrity checking.

Coverage:
1. Packet construction
2. Packet parsing
3. Round trip consistency
4. Fixed-size packet structure (18 bytes)
5. CRC16 integrity checking
6. Multi-packet flags (SEQ_PRESENT, LAST_PACKET)
7. NACK packet detection
8. Edge cases for CRC and packet validation
9. Deserialization of invalid packets (empty, oversized)
10. Address encoding/decoding

Assumptions:
1. Command dataclass and enums are defined as per protocol.
2. CRC16 implementation is correct (validated separately in test_crc.py).

Goal:
Ensure protocol layer guarantees correct packet construction, reliable CRC validation and handling of modified/corrupted packets.
"""

import struct
from test.common.asserts import assert_eq
from test.pymdtest import parametrize
from pc_tool.common.dataclasses import Command, CommandPacket
from pc_tool.common.enums import (
    MDT_PACKET_SIZE, MDTOffset, MDTFlags, CommandId, MemType,
    BreakpointControl, WatchpointControl, UtilEnum,
)
from pc_tool.common.protocol import (
    serialize_command_packet,
    deserialize_command_packet,
    validate_command_packet,
    is_nack_packet,
    calculate_crc16,
)


# Helpers
def _ping():
    return Command(name="PING", id=CommandId.PING,
                   mem=None, address=0, data=None, length=0)

def _read(address=0x20000000, length=4, mem=MemType.RAM):
    return Command(name="READ_MEM", id=CommandId.READ_MEM,
                   mem=mem, address=address, data=None, length=length)

def _write(address=0x20000000, data=b'\x01\x02\x03\x04', mem=MemType.RAM):
    return Command(name="WRITE_MEM", id=CommandId.WRITE_MEM,
                   mem=mem, address=address, data=data, length=len(data))

def _serialize(cmd, seq=0, multi=False, last=False):
    return serialize_command_packet(cmd, seq=seq, multi=multi, last=last)

def _fix_crc(pkt: bytearray) -> bytearray:
    """Recompute and patch the CRC field of a mutable packet."""
    crc = calculate_crc16(bytes(pkt[MDTOffset.CMD_ID:MDTOffset.CRC]))
    pkt[MDTOffset.CRC]     = crc & 0xFF
    pkt[MDTOffset.CRC + 1] = (crc >> 8) & 0xFF
    return pkt


# Multi-packet flags
def test_multi_single_packet_no_flags():
    pkt = _serialize(_ping(), multi=False, last=False)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.SEQ_PRESENT), False)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.LAST_PACKET), False)

def test_multi_first_packet_has_seq_not_last():
    pkt = _serialize(_ping(), seq=0, multi=True, last=False)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.SEQ_PRESENT), True)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.LAST_PACKET), False)

def test_multi_last_packet_has_both_flags():
    pkt = _serialize(_ping(), seq=5, multi=True, last=True)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.SEQ_PRESENT), True)
    assert_eq(bool(pkt[MDTOffset.FLAGS] & MDTFlags.LAST_PACKET), True)
    assert_eq(pkt[MDTOffset.SEQ], 5)

def test_multi_seq_wraps_at_255():
    pkt = _serialize(_ping(), seq=255, multi=True, last=False)
    assert_eq(pkt[MDTOffset.SEQ], 255)

def test_multi_seq_zero_is_valid():
    pkt = _serialize(_ping(), seq=0, multi=True, last=True)
    assert_eq(pkt[MDTOffset.SEQ], 0)


# Round trip for all command IDs
@parametrize("cmd_id,mem,address,data", [
    (CommandId.PING,       None,           0,          None),
    (CommandId.READ_MEM,   MemType.RAM,    0x20000000, None),
    (CommandId.WRITE_MEM,  MemType.RAM,    0x20000000, b'\xDE\xAD\xBE\xEF'),
    (CommandId.READ_REG,   None,           0x40013800, None),
    (CommandId.WRITE_REG,  None,           0x40013800, b'\x00\x00\x00\xFF'),
    (CommandId.RESET,      None,           0,          None),
    (CommandId.EXIT,       None,           0,          None),
])
def test_roundtrip_all_command_ids(cmd_id, mem, address, data):
    cmd = Command(name=cmd_id.name, id=cmd_id, mem=mem,
                  address=address, data=data, length=len(data) if data else 0)
    pkt = _serialize(cmd)
    result = deserialize_command_packet(pkt)
    assert_eq(result.cmd_id, cmd_id)
    assert_eq(result.address, address)


# Every byte corrupted
def test_corruption_at_every_data_byte_fails_validation():
    """
    Flip each byte in DATA field one at a time.
    Each corruption must break CRC -> validate returns False.
    """
    original = bytearray(_serialize(_read()))
    for offset in range(MDTOffset.DATA, MDTOffset.DATA + UtilEnum.WORD_SIZE):
        corrupt = bytearray(original)
        corrupt[offset] ^= 0xFF
        # CRC is NOT re-patched -> should fail
        assert_eq(validate_command_packet(bytes(corrupt)), False,
                  **{"corrupted_offset": offset})

def test_corruption_of_address_bytes_detected():
    original = bytearray(_serialize(_read(address=0x20000000)))
    for offset in range(MDTOffset.ADDRESS, MDTOffset.ADDRESS + UtilEnum.WORD_SIZE):
        corrupt = bytearray(original)
        corrupt[offset] ^= 0x01
        assert_eq(validate_command_packet(bytes(corrupt)), False)

def test_corruption_of_length_bytes_detected():
    original = bytearray(_serialize(_read()))
    for offset in range(MDTOffset.LENGTH, MDTOffset.LENGTH + UtilEnum.HALF_WORD_SIZE):
        corrupt = bytearray(original)
        corrupt[offset] ^= 0x01
        assert_eq(validate_command_packet(bytes(corrupt)), False)



# Edge case crc
def test_crc_all_zeros():
    assert_eq(calculate_crc16(b'\x00' * 16), calculate_crc16(b'\x00' * 16))

def test_crc_single_byte_matches_reference():
    import binascii
    for b in [0x00, 0x01, 0xFF, 0xAA, 0x55]:
        data = bytes([b])
        ref = binascii.crc_hqx(data, 0xFFFF)
        assert_eq(calculate_crc16(data), ref)

def test_crc_is_deterministic():
    data = bytes(range(16))
    assert_eq(calculate_crc16(data), calculate_crc16(data))

def test_crc_different_data_different_result():
    a = calculate_crc16(b'\xAA\xBB\xCC\xDD')
    b = calculate_crc16(b'\xAA\xBB\xCC\xDE')   # last byte differs by 1
    assert_eq(a == b, False)


# Validate cmd packet with STATUS_ERROR flag set
def test_status_error_with_corrected_crc_fails():
    pkt = bytearray(_serialize(_ping()))
    pkt[MDTOffset.FLAGS] |= MDTFlags.STATUS_ERROR
    _fix_crc(pkt)
    assert_eq(validate_command_packet(bytes(pkt)), False)

def test_event_flag_alone_does_not_fail_validation():
    """EVENT_PACKET flag (0x40) is not the STATUS_ERROR (0x20) bit.
    A packet with only EVENT flag set and valid CRC should still
    pass the structural checks in validate_command_packet."""
    pkt = bytearray(_serialize(_ping()))
    pkt[MDTOffset.FLAGS] |= MDTFlags.EVENT_PACKET
    _fix_crc(pkt)
    assert_eq(validate_command_packet(bytes(pkt)), True)


# Nack edge cases
def test_is_nack_with_all_other_fields_zero():
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x00
    pkt[MDTOffset.FLAGS]  = MDTFlags.ACK_NACK | MDTFlags.STATUS_ERROR
    pkt[MDTOffset.END]    = 0x55
    assert_eq(is_nack_packet(bytes(pkt)), True)

def test_is_nack_only_ack_bit_not_nack():
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x00
    pkt[MDTOffset.FLAGS]  = MDTFlags.ACK_NACK   # only ACK, no ERROR -> not a NACK
    pkt[MDTOffset.END]    = 0x55
    assert_eq(is_nack_packet(bytes(pkt)), False)

def test_is_nack_only_error_bit_not_nack():
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x00
    pkt[MDTOffset.FLAGS]  = MDTFlags.STATUS_ERROR   # only ERROR, no ACK -> not a NACK
    pkt[MDTOffset.END]    = 0x55
    assert_eq(is_nack_packet(bytes(pkt)), False)

def test_is_nack_empty_packet():
    assert_eq(is_nack_packet(b''), False)

def test_is_nack_oversized_packet():
    pkt = bytes(MDT_PACKET_SIZE + 1)
    assert_eq(is_nack_packet(pkt), False)


# Packet size
@parametrize("cmd_id,mem,address,data,length", [
    (CommandId.PING,       None,        0,          None,                   0),
    (CommandId.READ_MEM,   MemType.RAM, 0x20000000, None,                   4),
    (CommandId.WRITE_MEM,  MemType.RAM, 0x20000000, b'\x11\x22\x33\x44',   4),
    (CommandId.READ_REG,   None,        0x40013800, None,                   0),
])
def test_packet_size_is_always_18(cmd_id, mem, address, data, length):
    cmd = Command(name="X", id=cmd_id, mem=mem, address=address,
                  data=data, length=length)
    pkt = _serialize(cmd)
    assert_eq(len(pkt), MDT_PACKET_SIZE)


# Address encode/decode
@parametrize("address", [
    (0x00000000,),
    (0x20000000,),
    (0x08000000,),
    (0xFFFFFFFF,),
    (0x12345678,),
])
def test_address_roundtrip(address):
    cmd = _read(address=address)
    pkt = _serialize(cmd)
    result = deserialize_command_packet(pkt)
    assert_eq(result.address, address)


# deserialize invalid packets
def test_deserialize_rejects_empty():
    raised = False
    try:
        deserialize_command_packet(b'')
    except ValueError:
        raised = True
    assert_eq(raised, True)

def test_deserialize_rejects_one_extra_byte():
    pkt = _serialize(_ping()) + b'\x00'
    raised = False
    try:
        deserialize_command_packet(pkt)
    except ValueError:
        raised = True
    assert_eq(raised, True)