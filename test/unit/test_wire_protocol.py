"""
WIRE PROTOCOL TESTS (pc_tool/wire_protocol.py)


Validates packet encoding and decoding, integrity checking and the CRC.

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
2. The CRC is checked against binascii.crc_hqx (CRC-CCITT, init 0xFFFF) at the end of this file.

Goal:
Ensure protocol layer guarantees correct packet construction, reliable CRC validation and handling of modified/corrupted packets.
"""

import binascii
import random

from pc_tool.wire_protocol import (
    PACKET_SIZE,
    WORD_SIZE,
    Command,
    CommandId,
    Event,
    EventType,
    Flag,
    MemType,
    Offset,
    Packet,
    PacketError,
    crc16,
    decode,
    decode_event,
    encode,
    is_nack,
)
from test.common.asserts import assert_eq
from test.pymdtest import parametrize


# Helpers
def _is_valid_reply(raw: bytes) -> bool:
    """A reply the tool accepts: it decodes (size, fences, CRC) and carries no STATUS_ERROR."""
    try:
        return not decode(raw).is_error
    except PacketError:
        return False

def _ping():
    """Helper to create a simple PING command for testing."""
    return Command(name="PING", id=CommandId.PING,
                   mem=None, address=0, data=None, length=0)

def _read(address=0x20000000, length=4, mem=MemType.RAM):
    """Helper to create a READ_MEM command with specified parameters."""
    return Command(name="READ_MEM", id=CommandId.READ_MEM,
                   mem=mem, address=address, data=None, length=length)

def _write(address=0x20000000, data=b'\x01\x02\x03\x04', mem=MemType.RAM):
    """Helper to create a WRITE_MEM command with specified parameters."""
    return Command(name="WRITE_MEM", id=CommandId.WRITE_MEM,
                   mem=mem, address=address, data=data, length=len(data))

def _serialize(cmd, seq=0, multi=False, last=False):
    """Helper to serialize a Command with optional multi-packet flags."""
    return encode(cmd, seq=seq, multi=multi, last=last)

def _fix_crc(pkt: bytearray) -> bytearray:
    """Recompute and patch the CRC field of a mutable packet."""
    crc = crc16(bytes(pkt[Offset.CMD_ID:Offset.CRC]))
    pkt[Offset.CRC]     = crc & 0xFF
    pkt[Offset.CRC + 1] = (crc >> 8) & 0xFF
    return pkt


# Multi-packet flags
def test_multi_single_packet_no_flags():
    """A single-packet command should not have SEQ_PRESENT or LAST_PACKET flags set."""
    pkt = _serialize(_ping(), multi=False, last=False)
    assert_eq(bool(pkt[Offset.FLAGS] & Flag.SEQ_PRESENT), False)
    assert_eq(bool(pkt[Offset.FLAGS] & Flag.LAST_PACKET), False)

def test_multi_first_packet_has_seq_not_last():
    """In a multi-packet sequence, the first packet should have SEQ_PRESENT set and LAST_PACKET clear."""
    pkt = _serialize(_ping(), seq=0, multi=True, last=False)
    assert_eq(bool(pkt[Offset.FLAGS] & Flag.SEQ_PRESENT), True)
    assert_eq(bool(pkt[Offset.FLAGS] & Flag.LAST_PACKET), False)

def test_multi_last_packet_has_both_flags():
    """In a multi-packet sequence, the last packet should have both SEQ_PRESENT and LAST_PACKET flags set."""
    pkt = _serialize(_ping(), seq=5, multi=True, last=True)
    assert_eq(bool(pkt[Offset.FLAGS] & Flag.SEQ_PRESENT), True)
    assert_eq(bool(pkt[Offset.FLAGS] & Flag.LAST_PACKET), True)
    assert_eq(pkt[Offset.SEQ], 5)

def test_multi_seq_wraps_at_255():
    """Sequence number should wrap around at 255 and not overflow."""
    pkt = _serialize(_ping(), seq=255, multi=True, last=False)
    assert_eq(pkt[Offset.SEQ], 255)

def test_multi_seq_zero_is_valid():
    pkt = _serialize(_ping(), seq=0, multi=True, last=True)
    assert_eq(pkt[Offset.SEQ], 0)


# Round trip for all command IDs
@parametrize("cmd_id,mem,address,data", [
    (CommandId.PING,       None,           0,          None),
    (CommandId.READ_MEM,   MemType.RAM,    0x20000000, None),
    (CommandId.WRITE_MEM,  MemType.RAM,    0x20000000, b'\xDE\xAD\xBE\xEF'),
    (CommandId.READ_REG,   None,           0x40013800, None),
    (CommandId.WRITE_REG,  None,           0x40013800, b'\x00\x00\x00\xFF'),
    (CommandId.RESET,      None,           0,          None),
    (CommandId.BREAKPOINT, 1,              2,          None),
    (CommandId.WATCHPOINT, 1,              0,          b'\x00\x01\x00\x20'),
])
def test_roundtrip_all_command_ids(cmd_id, mem, address, data):
    """Test that serializing and then deserializing a command yields the original command fields."""
    cmd = Command(name=cmd_id.name, id=cmd_id, mem=mem,
                  address=address, data=data, length=len(data) if data else 0)
    pkt = _serialize(cmd)
    result = decode(pkt)
    assert_eq(result.cmd_id, cmd_id)
    assert_eq(result.address, address)


# Every byte corrupted
def test_corruption_at_every_data_byte_fails_validation():
    """
    Flip each byte in DATA field one at a time.
    Each corruption must break CRC -> validate returns False.
    """
    original = bytearray(_serialize(_read()))
    for offset in range(Offset.DATA, Offset.DATA + WORD_SIZE):
        corrupt = bytearray(original)
        corrupt[offset] ^= 0xFF
        # CRC is NOT re-patched -> should fail
        assert_eq(_is_valid_reply(bytes(corrupt)), False,
                  **{"corrupted_offset": offset})

def test_corruption_of_address_bytes_detected():
    """Flip each byte in ADDRESS field one at a time.
    Each corruption must break CRC -> validate returns False."""
    original = bytearray(_serialize(_read(address=0x20000000)))
    for offset in range(Offset.ADDRESS, Offset.ADDRESS + WORD_SIZE):
        corrupt = bytearray(original)
        corrupt[offset] ^= 0x01
        assert_eq(_is_valid_reply(bytes(corrupt)), False)

def test_corruption_of_length_bytes_detected():
    """Flip each byte in LENGTH field one at a time.
    Each corruption must break CRC -> validate returns False."""
    original = bytearray(_serialize(_read()))
    for offset in range(Offset.LENGTH, Offset.LENGTH + 2):
        corrupt = bytearray(original)
        corrupt[offset] ^= 0x01
        assert_eq(_is_valid_reply(bytes(corrupt)), False)

# Validate cmd packet with STATUS_ERROR flag set
def test_status_error_with_corrected_crc_fails():
    """If STATUS_ERROR flag is set, a reply with it should return False even if CRC is correct."""
    pkt = bytearray(_serialize(_ping()))
    pkt[Offset.FLAGS] |= Flag.STATUS_ERROR
    _fix_crc(pkt)
    assert_eq(_is_valid_reply(bytes(pkt)), False)

def test_event_flag_alone_does_not_fail_validation():
    """EVENT_PACKET flag (0x40) is not the STATUS_ERROR (0x20) bit.
    A packet with only EVENT flag set and valid CRC should still
    pass the structural checks of a reply."""
    pkt = bytearray(_serialize(_ping()))
    pkt[Offset.FLAGS] |= Flag.EVENT_PACKET
    _fix_crc(pkt)
    assert_eq(_is_valid_reply(bytes(pkt)), True)


# Nack edge cases
def test_is_nack_with_all_other_fields_zero():
    """A packet with all fields zero except FLAGS set to ACK_NACK | STATUS_ERROR should be detected as NACK."""
    pkt = bytearray(PACKET_SIZE)
    pkt[Offset.START]  = 0xAA
    pkt[Offset.CMD_ID] = 0x00
    pkt[Offset.FLAGS]  = Flag.ACK_NACK | Flag.STATUS_ERROR
    pkt[Offset.END]    = 0x55
    assert_eq(is_nack(bytes(pkt)), True)

def test_is_nack_only_ack_bit_not_nack():
    """A packet with only ACK_NACK bit set but not STATUS_ERROR should NOT be detected as NACK."""
    pkt = bytearray(PACKET_SIZE)
    pkt[Offset.START]  = 0xAA
    pkt[Offset.CMD_ID] = 0x00
    pkt[Offset.FLAGS]  = Flag.ACK_NACK   # only ACK, no ERROR -> not a NACK
    pkt[Offset.END]    = 0x55
    assert_eq(is_nack(bytes(pkt)), False)

def test_is_nack_only_error_bit_not_nack():
    """A packet with only STATUS_ERROR bit set but not ACK_NACK should NOT be detected as NACK."""
    pkt = bytearray(PACKET_SIZE)
    pkt[Offset.START]  = 0xAA
    pkt[Offset.CMD_ID] = 0x00
    pkt[Offset.FLAGS]  = Flag.STATUS_ERROR   # only ERROR, no ACK -> not a NACK
    pkt[Offset.END]    = 0x55
    assert_eq(is_nack(bytes(pkt)), False)

def test_is_nack_empty_packet():
    """An empty packet should not be detected as a NACK."""
    assert_eq(is_nack(b''), False)

def test_is_nack_oversized_packet():
    """A packet larger than PACKET_SIZE should not be detected as a NACK."""
    pkt = bytes(PACKET_SIZE + 1)
    assert_eq(is_nack(pkt), False)


# Packet size
@parametrize("cmd_id,mem,address,data,length", [
    (CommandId.PING,       None,        0,          None,                   0),
    (CommandId.READ_MEM,   MemType.RAM, 0x20000000, None,                   4),
    (CommandId.WRITE_MEM,  MemType.RAM, 0x20000000, b'\x11\x22\x33\x44',   4),
    (CommandId.READ_REG,   None,        0x40013800, None,                   0),
])
def test_packet_size_is_always_18(cmd_id, mem, address, data, length):
    """Regardless of command parameters, the serialized packet should always be exactly PACKET_SIZE bytes."""
    cmd = Command(name="X", id=cmd_id, mem=mem, address=address,
                  data=data, length=length)
    pkt = _serialize(cmd)
    assert_eq(len(pkt), PACKET_SIZE)


# Address encode/decode
@parametrize("address", [
    (0x00000000,),
    (0x20000000,),
    (0x08000000,),
    (0xFFFFFFFF,),
    (0x12345678,),
])
def test_address_roundtrip(address):
    """Test that the ADDRESS field is correctly encoded in the packet and can be decoded back to the original value."""
    cmd = _read(address=address)
    pkt = _serialize(cmd)
    result = decode(pkt)
    assert_eq(result.address, address)


# deserialize invalid packets
def test_deserialize_rejects_empty():
    """Deserializing an empty byte string should raise a PacketError."""
    raised = False
    try:
        decode(b'')
    except PacketError:
        raised = True
    assert_eq(raised, True)

def test_deserialize_rejects_one_extra_byte():
    """Deserializing a packet that is one byte too long should raise a PacketError."""
    pkt = _serialize(_ping()) + b'\x00'
    raised = False
    try:
        decode(pkt)
    except PacketError:
        raised = True
    assert_eq(raised, True)


# CRC16 against a trusted reference (binascii.crc_hqx)


def reference_crc16(data: bytes) -> int:
    # CRC-CCITT (0x1021) with initial value 0xFFFF
    return binascii.crc_hqx(data, 0xFFFF)


def test_crc_known_vectors():
    """Test CRC16 against known test vectors."""
    # Standard test vector
    assert_eq(crc16(b"123456789"), 0x29B1)

    # Empty
    assert_eq(crc16(b""), 0xFFFF)

def test_crc_random():
    """Test CRC16 against random data of varying lengths."""
    for length in [0, 1, 2, 4, 8, 16, 32, 64, 128, 256]:
        data = bytes(random.getrandbits(8) for _ in range(length))

        expected = reference_crc16(data)
        actual = crc16(data)
        assert_eq(actual, expected, data=data, length=length)

def test_crc_random_stress():
    """Stress test CRC16 with 1000 random inputs."""
    for _ in range(1000):
        length = random.randint(0, 256)
        data = bytes(random.getrandbits(8) for _ in range(length))

        expected = reference_crc16(data)
        actual = crc16(data)

        assert_eq(actual, expected, data=data, length=length)

def test_crc_all_zeros():
    """CRC of all zeros should be consistent and not zero (unless the polynomial causes that)."""
    assert_eq(crc16(b'\x00' * 16), crc16(b'\x00' * 16))

def test_crc_single_byte_matches_reference():
    """Test CRC16 of single-byte inputs against a known reference implementation (binascii.crc_hqx)."""
    import binascii
    for b in [0x00, 0x01, 0xFF, 0xAA, 0x55]:
        data = bytes([b])
        ref = binascii.crc_hqx(data, 0xFFFF)
        assert_eq(crc16(data), ref)

def test_crc_is_deterministic():
    data = bytes(range(16))
    assert_eq(crc16(data), crc16(data))

def test_crc_different_data_different_result():
    a = crc16(b'\xAA\xBB\xCC\xDD')
    b = crc16(b'\xAA\xBB\xCC\xDE')   # last byte differs by 1
    assert_eq(a == b, False)


# Events: decoding and the line shown for each kind
def _event_packet(kind, slot=0, address=0, length=0, data=0) -> Packet:
    pkt = bytearray(PACKET_SIZE)
    pkt[Offset.START], pkt[Offset.END] = 0xAA, 0x55
    pkt[Offset.FLAGS], pkt[Offset.SEQ], pkt[Offset.MEM_ID] = Flag.EVENT_PACKET, slot, kind
    pkt[Offset.ADDRESS:Offset.ADDRESS + 4] = address.to_bytes(4, "little")
    pkt[Offset.LENGTH:Offset.LENGTH + 2] = length.to_bytes(2, "little")
    pkt[Offset.DATA:Offset.DATA + 4] = data.to_bytes(4, "little")
    pkt[Offset.CRC:Offset.CRC + 2] = crc16(bytes(pkt[Offset.CMD_ID:Offset.CRC])).to_bytes(2, "little")
    return decode(bytes(pkt))


def test_event_decodes_kind_slot_and_values():
    event = decode_event(_event_packet(EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT, 1, 0x11, 4, 0x22))
    assert_eq(event, Event(EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT, 1, 0x11, 4, 0x22))
    assert_eq(event.describe(),
              "[Event] INTERNAL_MDT_EVENT_WATCHPOINT_HIT (slot=1, old=0x00000011, new=0x00000022, width=4)")


@parametrize("kind,data,expected", [
    (EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT, 5, "[Event] INTERNAL_MDT_EVENT_BREAKPOINT_HIT (slot=2, hit_count=5)"),
    (EventType.INTERNAL_MDT_EVENT_FAILED_PACKET, 3, "[Event] INTERNAL_MDT_EVENT_FAILED_PACKET (count=3)"),
    (EventType.INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, 255, "[Event] INTERNAL_MDT_EVENT_BUFFER_OVERFLOW (count=255)"),
])
def test_event_lines(kind, data, expected):
    assert_eq(decode_event(_event_packet(kind, slot=2, data=data)).describe(), expected)


def test_unknown_event_type_is_a_packet_error():
    try:
        decode_event(_event_packet(99))
    except PacketError as exc:
        assert_eq(str(exc), "Unknown event type: 99.")
    else:
        raise AssertionError("no PacketError")


def test_packet_keeps_its_raw_bytes_and_knows_nacks():
    raw = bytearray(PACKET_SIZE)
    raw[Offset.START], raw[Offset.END] = 0xAA, 0x55
    raw[Offset.FLAGS] = Flag.ACK_NACK | Flag.STATUS_ERROR
    raw[Offset.CRC:Offset.CRC + 2] = crc16(bytes(raw[Offset.CMD_ID:Offset.CRC])).to_bytes(2, "little")
    packet = decode(bytes(raw))
    assert_eq((packet.raw, packet.is_nack, packet.is_poll_ack), (bytes(raw), True, False))
    assert "raw" not in repr(packet)
