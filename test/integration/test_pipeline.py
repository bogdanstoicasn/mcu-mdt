from test.common.asserts import assert_eq
from test.pymdtest import parametrize

from pc_tool.common.dataclasses import Command, CommandPacket
from pc_tool.common.enums import (
    MDT_PACKET_SIZE, MDTOffset, MDTFlags,
    CommandId, MemType, BreakpointControl, WatchpointControl,
    UtilEnum, EventType,
)
from pc_tool.common.protocol import (
    calculate_crc16,
    serialize_command_packet,
    deserialize_command_packet,
    validate_command_packet,
    is_nack_packet,
)
from pc_tool.parser import parse_line
from pc_tool.validator import validate_commands


# Fixtures
COMMANDS = {
    "PING":       {"id": 0x05, "params": []},
    "RESET":      {"id": 0x06, "params": []},
    "READ_MEM": {
        "id": 0x01,
        "params": [
            {"name": "control_value", "type": "str"},
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "len",           "type": "uint32", "format": "dec"},
        ],
    },
    "WRITE_MEM": {
        "id": 0x02,
        "params": [
            {"name": "control_value", "type": "str"},
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "len",           "type": "uint32", "format": "dec"},
            {"name": "data",          "type": "bytes"},
        ],
    },
    "READ_REG": {
        "id": 0x03,
        "params": [{"name": "address", "type": "uint32_or_str", "format": "hex"}],
    },
    "WRITE_REG": {
        "id": 0x04,
        "params": [
            {"name": "address", "type": "uint32_or_str", "format": "hex"},
            {"name": "data",    "type": "bytes"},
        ],
    },
    "BREAKPOINT": {
        "id": 0x07,
        "params": [
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "control_value", "type": "str"},
        ],
    },
    "WATCHPOINT": {
        "id": 0x08,
        "params": [
            {"name": "address",       "type": "uint32", "format": "hex"},
            {"name": "control_value", "type": "str"},
            {"name": "wp_data",       "type": "uint32", "format": "hex"},
        ],
    },
}

CONTROL_VALUES = {
    "RAM": 0, "FLASH": 1, "EEPROM": 2,
    "DISABLED": 0, "ENABLED": 1, "RESET": 2, "NEXT": 3, "MASK": 3,
}

MCU_METADATA_RAM = {
    "memories": {
        "IRAM": {"type": "ram", "start": 0x20000000, "size": 0x5000},
    },
    "modules": {},
}

MCU_METADATA_REG = {
    "memories": {},
    "modules": {
        "USART1": {
            "instances": [{"register_group": "USART1", "offset": 0x40013800}],
            "register_groups": {
                "USART1": {
                    "offset": 0x40013800,
                    "registers": {
                        "SR":  {"offset": 0x00, "size": 32, "rw": "read-write"},
                        "DR":  {"offset": 0x04, "size": 32, "rw": "read-write"},
                        "BRR": {"offset": 0x08, "size": 32, "rw": "read-write"},
                    },
                }
            },
        }
    },
}


# Mock infrastructure
class MockUART:
    """Perfect byte-level loopback, bytes written are instantly readable."""

    def __init__(self):
        self._buf = bytearray()

    def write(self, data: bytes):
        self._buf.extend(data)

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:n])
        self._buf = self._buf[n:]
        return chunk

    def read_packet(self) -> bytes:
        return self.read(MDT_PACKET_SIZE)

    @property
    def pending(self) -> int:
        return len(self._buf)


def _make_ack_packet(for_cmd_id: int) -> bytes:
    """Build a minimal ACK response the MCU would send back."""
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = for_cmd_id
    pkt[MDTOffset.FLAGS]  = MDTFlags.ACK_NACK   # ACK bit set, ERROR bit clear
    pkt[MDTOffset.END]    = 0x55
    crc = calculate_crc16(bytes(pkt[MDTOffset.CMD_ID:MDTOffset.CRC]))
    pkt[MDTOffset.CRC]     = crc & 0xFF
    pkt[MDTOffset.CRC + 1] = (crc >> 8) & 0xFF
    return bytes(pkt)


def _make_nack_packet() -> bytes:
    """Build a NACK response (cmd_id=0, ACK+ERROR flags set)."""
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x00
    pkt[MDTOffset.FLAGS]  = MDTFlags.ACK_NACK | MDTFlags.STATUS_ERROR
    pkt[MDTOffset.END]    = 0x55
    crc = calculate_crc16(bytes(pkt[MDTOffset.CMD_ID:MDTOffset.CRC]))
    pkt[MDTOffset.CRC]     = crc & 0xFF
    pkt[MDTOffset.CRC + 1] = (crc >> 8) & 0xFF
    return bytes(pkt)


def _make_event_packet(event_type: EventType, bp_id: int = 0) -> bytes:
    """Build an unsolicited breakpoint event packet."""
    pkt = bytearray(MDT_PACKET_SIZE)
    pkt[MDTOffset.START]  = 0xAA
    pkt[MDTOffset.CMD_ID] = 0x00
    pkt[MDTOffset.FLAGS]  = MDTFlags.EVENT_PACKET
    pkt[MDTOffset.SEQ]    = bp_id
    # Pack event type into data field
    event_bytes = event_type.to_bytes(4, "little")
    pkt[MDTOffset.DATA:MDTOffset.DATA + 4] = event_bytes
    pkt[MDTOffset.END]    = 0x55
    crc = calculate_crc16(bytes(pkt[MDTOffset.CMD_ID:MDTOffset.CRC]))
    pkt[MDTOffset.CRC]     = crc & 0xFF
    pkt[MDTOffset.CRC + 1] = (crc >> 8) & 0xFF
    return bytes(pkt)


def _full_pipeline(line: str, meta: dict, uart: MockUART,
                   seq=0, multi=False, last=False) -> CommandPacket | None:
    """
    Run the complete PC-side pipeline for a single CLI line:
      parse -> validate -> serialize -> write to UART -> read back -> deserialize.

    Returns the deserialized CommandPacket, or None if any stage rejects.
    """
    cmd = parse_line(line, COMMANDS, CONTROL_VALUES, meta)
    if cmd is None:
        return None

    if not validate_commands(cmd, meta):
        return None

    pkt = serialize_command_packet(cmd, seq=seq, multi=multi, last=last)
    uart.write(pkt)

    raw = uart.read_packet()
    return deserialize_command_packet(raw)


# Every command end-to-end
def test_e2e_ping():
    uart = MockUART()
    cmd = parse_line("PING", COMMANDS, CONTROL_VALUES, {})
    pkt = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    uart.write(pkt)
    received = deserialize_command_packet(uart.read_packet())
    assert_eq(received.cmd_id, CommandId.PING)

def test_e2e_read_mem():
    uart = MockUART()
    result = _full_pipeline("READ_MEM RAM 0x20000000 4", MCU_METADATA_RAM, uart)
    assert_eq(result.cmd_id, CommandId.READ_MEM)
    assert_eq(result.address, 0x20000000)
    assert_eq(result.length,  4)
    assert_eq(result.mem_id,  MemType.RAM)

def test_e2e_write_mem():
    uart = MockUART()
    result = _full_pipeline("WRITE_MEM RAM 0x20000010 4 DEADBEEF", MCU_METADATA_RAM, uart)
    assert_eq(result.cmd_id, CommandId.WRITE_MEM)
    assert_eq(result.address, 0x20000010)
    assert_eq(result.data,    b'\xDE\xAD\xBE\xEF')

def test_e2e_read_reg_by_address():
    uart = MockUART()
    result = _full_pipeline("READ_REG 0x40013800", MCU_METADATA_REG, uart)
    assert_eq(result.cmd_id, CommandId.READ_REG)
    assert_eq(result.address, 0x40013800)

def test_e2e_write_reg_by_address():
    uart = MockUART()
    result = _full_pipeline("WRITE_REG 0x40013804 000000FF", MCU_METADATA_REG, uart)
    assert_eq(result.cmd_id, CommandId.WRITE_REG)
    assert_eq(result.address, 0x40013804)
    assert_eq(result.data,    b'\x00\x00\x00\xFF')

def test_e2e_breakpoint_enable():
    uart = MockUART()
    cmd = parse_line("BREAKPOINT 0 ENABLED", COMMANDS, CONTROL_VALUES, {})
    pkt = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    uart.write(pkt)
    received = deserialize_command_packet(uart.read_packet())
    assert_eq(received.cmd_id, CommandId.BREAKPOINT)
    assert_eq(received.address, 0)
    assert_eq(received.mem_id,  BreakpointControl.ENABLED)

def test_e2e_watchpoint_enable():
    uart = MockUART()
    cmd = parse_line("WATCHPOINT 0 ENABLED 0x20000100", COMMANDS, CONTROL_VALUES, {})
    pkt = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    uart.write(pkt)
    received = deserialize_command_packet(uart.read_packet())
    assert_eq(received.cmd_id, CommandId.WATCHPOINT)
    assert_eq(received.address, 0)
    assert_eq(received.mem_id,  WatchpointControl.ENABLED)

def test_e2e_packet_is_validated_after_loopback():
    uart = MockUART()
    cmd = parse_line("PING", COMMANDS, CONTROL_VALUES, {})
    pkt = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    uart.write(pkt)
    raw = uart.read_packet()
    assert_eq(validate_command_packet(raw), True)


# Multi-packet sequences
def _chunk_transfer(address: int, payload: bytes, uart: MockUART) -> list[CommandPacket]:
    """
    Split a payload into 4-byte chunks and serialize each as a
    multi-packet sequence. Returns a list of deserialized packets.
    """
    chunk_size = UtilEnum.WORD_SIZE
    chunks = [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)]
    received = []

    for i, chunk in enumerate(chunks):
        # Pad last chunk if necessary
        padded = chunk.ljust(chunk_size, b'\x00')
        is_last = (i == len(chunks) - 1)
        cmd = Command(
            name="WRITE_MEM", id=CommandId.WRITE_MEM,
            mem=MemType.RAM,
            address=address + i * chunk_size,
            data=padded,
            length=len(chunk),
        )
        pkt = serialize_command_packet(cmd, seq=i, multi=True, last=is_last)
        uart.write(pkt)
        received.append(deserialize_command_packet(uart.read_packet()))

    return received

def test_chunked_transfer_16_bytes():
    uart = MockUART()
    payload = bytes(range(16))       # 4 chunks of 4 bytes
    packets = _chunk_transfer(0x20000000, payload, uart)

    assert_eq(len(packets), 4)

    # Sequence numbers 0..3
    for i, pkt in enumerate(packets):
        assert_eq(pkt.seq, i)

    # SEQ_PRESENT on all; LAST_PACKET only on the last one
    for pkt in packets:
        uart2 = MockUART()
        cmd = Command(name="WRITE_MEM", id=CommandId.WRITE_MEM,
                      mem=MemType.RAM, address=0x20000000,
                      data=b'\x00\x00\x00\x00', length=4)
        raw = serialize_command_packet(cmd, seq=pkt.seq, multi=True,
                                       last=(pkt.seq == 3))
        assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.SEQ_PRESENT), True)

    last_raw = serialize_command_packet(
        Command(name="X", id=CommandId.WRITE_MEM, mem=MemType.RAM,
                address=0x2000000C, data=bytes(range(12, 16)), length=4),
        seq=3, multi=True, last=True
    )
    assert_eq(bool(last_raw[MDTOffset.FLAGS] & MDTFlags.LAST_PACKET), True)

def test_chunked_transfer_single_chunk_is_last():
    uart = MockUART()
    payload = b'\xAA\xBB\xCC\xDD'   # exactly one chunk
    packets = _chunk_transfer(0x20000000, payload, uart)
    assert_eq(len(packets), 1)
    assert_eq(packets[0].seq, 0)

def test_chunked_transfer_addresses_increment_correctly():
    uart = MockUART()
    payload = bytes(range(8))        # 2 chunks
    packets = _chunk_transfer(0x20000000, payload, uart)
    assert_eq(packets[0].address, 0x20000000)
    assert_eq(packets[1].address, 0x20000004)


# Validation rejects bad commands before they hit the wire
def test_validator_blocks_out_of_range_read():
    uart = MockUART()
    # 0xDEADBEEF is not in any known memory segment
    result = _full_pipeline("READ_MEM RAM 0xDEADBEEF 4", MCU_METADATA_RAM, uart)
    assert_eq(result, None)
    assert_eq(uart.pending, 0)   # nothing was written to the wire

def test_validator_blocks_invalid_breakpoint_id():
    # ID 99 is way out of range (max is MDT_MAX_BREAKPOINTS-1 = 3)
    cmd = parse_line("BREAKPOINT 99 ENABLED", COMMANDS, CONTROL_VALUES, {})
    # parse_line treats the address as a hex uint32 — 99 decimal = 0x63 hex
    # but validate_commands checks it is < MDT_MAX_BREAKPOINTS
    from pc_tool.validator import validate_breakpoint
    assert_eq(validate_breakpoint(cmd), False)

def test_validator_blocks_unaligned_watchpoint():
    uart = MockUART()
    # 0x20000001 is not 4-byte aligned
    cmd = parse_line("WATCHPOINT 0 ENABLED 0x20000001", COMMANDS, CONTROL_VALUES, {})
    from pc_tool.validator import validate_watchpoint
    assert_eq(validate_watchpoint(cmd), False)

def test_validator_blocks_write_to_nonexistent_register():
    cmd = Command(name="WRITE_REG", id=CommandId.WRITE_REG,
                  address=0xDEADBEEF, data=b'\x00\x00\x00\x00', length=4)
    assert_eq(validate_commands(cmd, MCU_METADATA_REG), False)

def test_validator_passes_valid_command_through():
    uart = MockUART()
    result = _full_pipeline("READ_MEM RAM 0x20001000 4", MCU_METADATA_RAM, uart)
    assert_eq(result is not None, True)
    assert_eq(uart.pending, 0)   # packet was consumed


# Bad-packet resilience -> MCU response handling
def test_ack_from_mcu_is_valid_packet():
    ack = _make_ack_packet(CommandId.PING)
    assert_eq(validate_command_packet(ack), True)

def test_nack_from_mcu_is_recognised():
    nack = _make_nack_packet()
    assert_eq(is_nack_packet(nack), True)
    assert_eq(validate_command_packet(nack), False)  # STATUS_ERROR invalid

def test_corrupted_mcu_response_fails_validation():
    ack = bytearray(_make_ack_packet(CommandId.READ_MEM))
    ack[MDTOffset.DATA] ^= 0xFF   # corrupt data without patching CRC
    assert_eq(validate_command_packet(bytes(ack)), False)

def test_truncated_mcu_response_fails_validation():
    ack = _make_ack_packet(CommandId.PING)[:-1]   # drop last byte
    assert_eq(validate_command_packet(ack), False)

def test_mcu_response_with_wrong_start_byte_fails():
    ack = bytearray(_make_ack_packet(CommandId.PING))
    ack[MDTOffset.START] = 0x00
    assert_eq(validate_command_packet(bytes(ack)), False)

def test_pipeline_sends_exactly_one_packet_per_command():
    uart = MockUART()
    cmd = parse_line("PING", COMMANDS, CONTROL_VALUES, {})
    pkt = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    uart.write(pkt)
    assert_eq(uart.pending, MDT_PACKET_SIZE)
    uart.read_packet()
    assert_eq(uart.pending, 0)


# Event packets
def test_event_packet_has_event_flag_set():
    evt = _make_event_packet(EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT, bp_id=2)
    flags = evt[MDTOffset.FLAGS]
    assert_eq(bool(flags & MDTFlags.EVENT_PACKET), True)

def test_event_packet_does_not_look_like_nack():
    evt = _make_event_packet(EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT)
    assert_eq(is_nack_packet(evt), False)

def test_event_packet_carries_breakpoint_id():
    bp_id = 3
    evt = _make_event_packet(EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT, bp_id=bp_id)
    assert_eq(evt[MDTOffset.SEQ], bp_id)

def test_event_packet_carries_event_type_in_data():
    evt = _make_event_packet(EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT)
    event_type_raw = int.from_bytes(
        evt[MDTOffset.DATA:MDTOffset.DATA + 4], byteorder="little"
    )
    assert_eq(event_type_raw, EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT)

def test_event_packet_crc_is_valid():
    evt = _make_event_packet(EventType.INTERNAL_MDT_EVENT_BUFFER_OVERFLOW)
    crc_recv = int.from_bytes(evt[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
    crc_calc  = calculate_crc16(evt[MDTOffset.CMD_ID:MDTOffset.CRC])
    assert_eq(crc_recv, crc_calc)

def test_buffer_overflow_event_is_recognised():
    evt = _make_event_packet(EventType.INTERNAL_MDT_EVENT_BUFFER_OVERFLOW)
    flags = evt[MDTOffset.FLAGS]
    assert_eq(bool(flags & MDTFlags.EVENT_PACKET), True)
    event_type_raw = int.from_bytes(
        evt[MDTOffset.DATA:MDTOffset.DATA + 4], byteorder="little"
    )
    assert_eq(event_type_raw, EventType.INTERNAL_MDT_EVENT_BUFFER_OVERFLOW)


# Round-trip field fidelity
@parametrize("address,mem,length", [
    (0x20000000, MemType.RAM,    1),
    (0x20001000, MemType.RAM,    4),
    (0x20004FFC, MemType.RAM,    4),   # near top of 20 KB region
    (0x08000000, MemType.FLASH,  4),
])
def test_field_fidelity_address_mem_length(address, mem, length):
    cmd = Command(name="READ_MEM", id=CommandId.READ_MEM,
                  mem=mem, address=address, data=None, length=length)
    pkt  = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    back = deserialize_command_packet(pkt)
    assert_eq(back.address, address)
    assert_eq(back.mem_id,  mem)
    assert_eq(back.length,  min(length, UtilEnum.WORD_SIZE))

@parametrize("data", [
    (b'\x00\x00\x00\x00',),
    (b'\xFF\xFF\xFF\xFF',),
    (b'\xDE\xAD\xBE\xEF',),
    (b'\x01\x02\x03\x04',),
    (b'\xAA\x55\xAA\x55',),
])
def test_field_fidelity_data(data):
    cmd  = Command(name="WRITE_MEM", id=CommandId.WRITE_MEM,
                   mem=MemType.RAM, address=0x20000000, data=data, length=4)
    pkt  = serialize_command_packet(cmd, seq=0, multi=False, last=False)
    back = deserialize_command_packet(pkt)
    assert_eq(back.data, data)

@parametrize("seq", [(0,), (1,), (127,), (255,)])
def test_field_fidelity_seq(seq):
    cmd  = Command(name="PING", id=CommandId.PING,
                   mem=None, address=0, data=None, length=0)
    pkt  = serialize_command_packet(cmd, seq=seq, multi=True, last=False)
    back = deserialize_command_packet(pkt)
    assert_eq(back.seq, seq)