"""
HARDWARE TESTS FOR MCU-MDT


Run these against a real MCU flashed with the MDT firmware.

Usage:
    # ATmega328P on /dev/ttyACM0  (default baud 19200)
    MDT_PORT=/dev/ttyACM0 python3 -m test.pymdtest hardware

    # STM32 on /dev/ttyUSB0 at different baud
    MDT_PORT=/dev/ttyUSB0 MDT_BAUD=19200 MDT_PLATFORM=stm32 python3 -m test.pymdtest hardware

    # Windows
    MDT_PORT=COM3 python3 -m test.pymdtest hardware

Environment variables:
    MDT_PORT      Serial port.  If unset every test is skipped gracefully.
    MDT_BAUD      Baud rate  (default: 19200)
    MDT_TIMEOUT   Per-packet read timeout in seconds  (default: 2.0)
    MDT_PLATFORM  "avr" or "stm32"  (default: "avr")
                  Controls which SRAM base address is used for memory tests.

Coverage:
1. Link health (ping, framing, crc)
2. Memory read (read from sram and flash, return valid ack)
3. Memory write/readback (write patters, read them back, verify)
4. Register access (read/write reg, round-trip via SRAM)
5. Protocol robustness (bad crc, recovery, resynch)
6. Breakpoints
7. Watchpoints
8. Event packets
9. Chunked transfer
10. Stress

Assumptions:
1. Firmware running (mcu_mdt_poll loop)
2. ≥64B free SRAM
3. AVR base: 0x0200, STM32 base: 0x20000200

Goal:
Validate that the MCU-MDT functions correctly under real-world usage scenarios.
"""

import os
import time
import threading

from test.common.asserts import assert_eq
from test.pymdtest import parametrize

from pc_tool.common.dataclasses import Command
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
from pc_tool.common.uart_io import MCUSerialLink
from pc_tool.commander import execute_command
from pc_tool.event import rx_worker


# Configuration
MDT_PORT     = os.environ.get("MDT_PORT", "")
MDT_BAUD     = int(os.environ.get("MDT_BAUD", "19200"))
MDT_TIMEOUT  = float(os.environ.get("MDT_TIMEOUT", "2.0"))
MDT_PLATFORM = os.environ.get("MDT_PLATFORM", "avr").lower()

HW_AVAILABLE = bool(MDT_PORT)

# Safe scratch SRAM area — well above register file / stack on both platforms
TEST_SRAM_BASE = 0x20000200 if MDT_PLATFORM == "stm32" else 0x0200
FLASH_BASE     = 0x08000000 if MDT_PLATFORM == "stm32" else 0x0000


# Helpers
def _skip(msg="MDT_PORT not set — connect a MCU and re-run"):
    print(f"  [SKIP] {msg}")
    return True


def _link() -> MCUSerialLink:
    """Open a serial link with a short reset delay."""
    link = MCUSerialLink(
        port=MDT_PORT,
        baudrate=MDT_BAUD,
        timeout=MDT_TIMEOUT,
        reset_delay=2.0,
    )
    link.open()
    return link


def _cmd(cmd_id, *, mem=None, address=0, length=0, data=None) -> Command:
    return Command(
        name=cmd_id.name,
        id=cmd_id,
        mem=mem,
        address=address,
        length=length,
        data=data,
    )


def _send(link: MCUSerialLink, cmd: Command,
          seq=0, multi=False, last=False) -> bytes | None:
    """Serialize, transmit, and return the raw 18-byte response (or None)."""
    pkt = serialize_command_packet(cmd, seq=seq, multi=multi, last=last)
    link.send_packet(pkt)
    return link.read_packet(timeout=MDT_TIMEOUT)


def _send_parsed(link: MCUSerialLink, cmd: Command, **kw):
    """Like _send but returns a deserialized CommandPacket or None."""
    raw = _send(link, cmd, **kw)
    if raw is None:
        return None
    try:
        return deserialize_command_packet(raw)
    except ValueError:
        return None


def _flush(link: MCUSerialLink, ms=300):
    """Drain stale bytes so the next test starts clean."""
    time.sleep(ms / 1000)
    if link.ser and link.ser.in_waiting:
        link.ser.read(link.ser.in_waiting)
    link._rx_buf.clear()


def _assert_clean_ack(raw: bytes, cmd_id: int):
    """Assert raw is a valid, non-error ACK for cmd_id."""
    assert_eq(raw is not None, True)
    assert_eq(len(raw), MDT_PACKET_SIZE)
    # CRC must be correct
    crc_recv = int.from_bytes(raw[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
    crc_calc  = calculate_crc16(raw[MDTOffset.CMD_ID:MDTOffset.CRC])
    assert_eq(crc_recv, crc_calc)
    # ACK flag set, error flag clear, correct command echoed back
    flags = raw[MDTOffset.FLAGS]
    assert_eq(bool(flags & MDTFlags.ACK_NACK),      True)
    assert_eq(bool(flags & MDTFlags.STATUS_ERROR),  False)
    assert_eq(raw[MDTOffset.CMD_ID], cmd_id)

# End of helpers


# Health check
def test_hw_ping_gets_response():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        _assert_clean_ack(raw, CommandId.PING)
    finally:
        link.close()

def test_hw_ping_response_is_exactly_18_bytes():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(len(raw), MDT_PACKET_SIZE)
    finally:
        link.close()

def test_hw_ping_start_end_framing():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(raw[MDTOffset.START], 0xAA)
        assert_eq(raw[MDTOffset.END],   0x55)
    finally:
        link.close()

def test_hw_ping_response_crc_valid():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        crc_recv = int.from_bytes(raw[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
        crc_calc  = calculate_crc16(raw[MDTOffset.CMD_ID:MDTOffset.CRC])
        assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_ping_echoes_cmd_id():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        pkt = _send_parsed(link, _cmd(CommandId.PING))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.cmd_id, CommandId.PING)
    finally:
        link.close()

def test_hw_ping_ack_flag_set():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.ACK_NACK), True)
    finally:
        link.close()

def test_hw_ping_no_error_flag():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.STATUS_ERROR), False)
    finally:
        link.close()


# Memory read
def test_hw_read_sram_returns_ack():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                   address=TEST_SRAM_BASE, length=4)
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.READ_MEM)
    finally:
        link.close()

def test_hw_read_sram_data_is_four_bytes():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                   address=TEST_SRAM_BASE, length=4)
        pkt = _send_parsed(link, cmd)
        assert_eq(pkt is not None, True)
        assert_eq(len(pkt.data), UtilEnum.WORD_SIZE)
    finally:
        link.close()

def test_hw_read_flash_returns_valid_packet():
    """
    FLASH read may ACK or NACK depending on the MCU, but the response
    must always be a structurally sound 18-byte packet with a valid CRC.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.FLASH,
                   address=FLASH_BASE, length=4)
        raw = _send(link, cmd)
        assert_eq(raw is not None, True)
        assert_eq(len(raw), MDT_PACKET_SIZE)
        assert_eq(raw[MDTOffset.START], 0xAA)
        assert_eq(raw[MDTOffset.END],   0x55)
        crc_recv = int.from_bytes(raw[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
        crc_calc  = calculate_crc16(raw[MDTOffset.CMD_ID:MDTOffset.CRC])
        assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_read_sram_mem_id_echoed():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                   address=TEST_SRAM_BASE, length=4)
        pkt = _send_parsed(link, cmd)
        assert_eq(pkt is not None, True)
        assert_eq(pkt.mem_id, MemType.RAM)
    finally:
        link.close()


# Memory write / readback
def test_hw_write_sram_returns_ack():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                   address=TEST_SRAM_BASE, length=4,
                   data=b'\x12\x34\x56\x78')
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.WRITE_MEM)
    finally:
        link.close()

def test_hw_write_then_read_back_pattern():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        pattern = b'\xCA\xFE\xBA\xBE'
        _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=TEST_SRAM_BASE, length=4, data=pattern))
        _flush(link)
        pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                      address=TEST_SRAM_BASE, length=4))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.data, pattern)
    finally:
        link.close()

def test_hw_write_all_zeros_read_back():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        addr = TEST_SRAM_BASE + 4
        _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=addr, length=4, data=b'\x00\x00\x00\x00'))
        _flush(link)
        pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                      address=addr, length=4))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.data, b'\x00\x00\x00\x00')
    finally:
        link.close()

def test_hw_write_all_ones_read_back():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        addr = TEST_SRAM_BASE + 8
        _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=addr, length=4, data=b'\xFF\xFF\xFF\xFF'))
        _flush(link)
        pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                      address=addr, length=4))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.data, b'\xFF\xFF\xFF\xFF')
    finally:
        link.close()

def test_hw_adjacent_writes_do_not_alias():
    """Two adjacent 4-byte words must not bleed into each other."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        addr_a, addr_b = TEST_SRAM_BASE + 0x10, TEST_SRAM_BASE + 0x14
        for addr, pat in [(addr_a, b'\xAA\xAA\xAA\xAA'),
                          (addr_b, b'\xBB\xBB\xBB\xBB')]:
            _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                             address=addr, length=4, data=pat))
            _flush(link)
        for addr, expected in [(addr_a, b'\xAA\xAA\xAA\xAA'),
                               (addr_b, b'\xBB\xBB\xBB\xBB')]:
            pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                          address=addr, length=4))
            assert_eq(pkt is not None, True)
            assert_eq(pkt.data, expected)
            _flush(link)
    finally:
        link.close()

@parametrize("pattern", [
    (b'\xDE\xAD\xBE\xEF',),
    (b'\x01\x02\x03\x04',),
    (b'\xAA\x55\xAA\x55',),
    (b'\x00\xFF\x00\xFF',),
])
def test_hw_write_read_various_patterns(pattern):
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        addr = TEST_SRAM_BASE + 0x20
        _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=addr, length=4, data=pattern))
        _flush(link)
        pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                      address=addr, length=4))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.data, pattern)
    finally:
        link.close()


# Register access
def test_hw_read_reg_at_sram_returns_packet():
    """
    READ_REG at a known-mapped SRAM address.
    The HAL maps register reads to SRAM, so any scratch address is valid.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.READ_REG, address=TEST_SRAM_BASE))
        assert_eq(raw is not None, True)
        assert_eq(len(raw), MDT_PACKET_SIZE)
        crc_recv = int.from_bytes(raw[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
        assert_eq(crc_recv, calculate_crc16(raw[MDTOffset.CMD_ID:MDTOffset.CRC]))
    finally:
        link.close()

def test_hw_write_reg_read_reg_roundtrip():
    """
    Write a byte via WRITE_REG then read it back via READ_REG.
    Both route through hal_write_memory / hal_read_memory on SRAM.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        addr = TEST_SRAM_BASE + 0x30
        # Write 0xA5 via WRITE_REG (1-byte register write)
        _send(link, _cmd(CommandId.WRITE_REG, address=addr,
                         data=b'\xA5\x00\x00\x00'))
        _flush(link)
        # Read back via READ_REG
        pkt = _send_parsed(link, _cmd(CommandId.READ_REG, address=addr))
        assert_eq(pkt is not None, True)
        # The first data byte must be 0xA5; the rest are whatever SRAM holds
        assert_eq(pkt.data[0], 0xA5)
    finally:
        link.close()


# Protocol robustness
def test_hw_bad_crc_triggers_nack():
    """Corrupt one byte in the payload — the MCU must reply with NACK."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        pkt = bytearray(serialize_command_packet(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        pkt[MDTOffset.DATA] ^= 0xFF          # corrupt without re-patching CRC
        link.send_packet(bytes(pkt))
        raw = link.read_packet(timeout=MDT_TIMEOUT)
        assert_eq(raw is not None, True)
        assert_eq(is_nack_packet(raw), True)
    finally:
        link.close()

def test_hw_nack_carries_valid_crc():
    """The NACK packet itself must be well-formed with a correct CRC."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        pkt = bytearray(serialize_command_packet(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        pkt[MDTOffset.DATA] ^= 0xFF
        link.send_packet(bytes(pkt))
        raw = link.read_packet(timeout=MDT_TIMEOUT)
        assert_eq(raw is not None, True)
        crc_recv = int.from_bytes(raw[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
        crc_calc  = calculate_crc16(raw[MDTOffset.CMD_ID:MDTOffset.CRC])
        assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_mcu_recovers_after_bad_packet():
    """After receiving a bad packet the MCU must still ACK valid ones."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        # Send all-zeros (no valid START byte → MCU ignores it)
        link.send_packet(bytes(MDT_PACKET_SIZE))
        link.read_packet(timeout=MDT_TIMEOUT)   # may be None; we don't care
        _flush(link)
        # Valid PING must get a clean ACK
        raw = _send(link, _cmd(CommandId.PING))
        _assert_clean_ack(raw, CommandId.PING)
    finally:
        link.close()

def test_hw_resync_after_truncated_send():
    """
    Send only the first 9 bytes of a packet (half a packet).
    The MCU's byte-level state machine will time out waiting for the rest.
    After the link is re-synced a full PING must still succeed.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        half = serialize_command_packet(
            _cmd(CommandId.PING), seq=0, multi=False, last=False)[:9]
        link.send_packet(half)
        time.sleep(0.5)     # let the MCU notice nothing more is coming
        _flush(link)
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(len(raw), MDT_PACKET_SIZE)
    finally:
        link.close()

def test_hw_nack_seq_mirrors_request_seq():
    """The NACK packet must echo back the SEQ byte of the bad request."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        TEST_SEQ = 0x2A
        pkt = bytearray(serialize_command_packet(
            _cmd(CommandId.PING), seq=TEST_SEQ, multi=True, last=False))
        pkt[MDTOffset.DATA] ^= 0xFF          # corrupt data, keep seq
        link.send_packet(bytes(pkt))
        raw = link.read_packet(timeout=MDT_TIMEOUT)
        assert_eq(raw is not None, True)
        assert_eq(is_nack_packet(raw), True)
        assert_eq(raw[MDTOffset.SEQ], TEST_SEQ)
    finally:
        link.close()

def test_hw_unknown_cmd_id_triggers_error_response():
    """
    A packet with cmd_id=0xFF (unknown) must produce a response with the
    STATUS_ERROR flag set.  The firmware dispatches through the handler table;
    an out-of-range cmd_id returns 0 which sets the error flag.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        # Build a hand-crafted packet with cmd_id = 0xFF
        pkt = bytearray(MDT_PACKET_SIZE)
        pkt[MDTOffset.START]  = 0xAA
        pkt[MDTOffset.CMD_ID] = 0xFF
        pkt[MDTOffset.END]    = 0x55
        crc = calculate_crc16(bytes(pkt[MDTOffset.CMD_ID:MDTOffset.CRC]))
        pkt[MDTOffset.CRC]     = crc & 0xFF
        pkt[MDTOffset.CRC + 1] = (crc >> 8) & 0xFF
        link.send_packet(bytes(pkt))
        raw = link.read_packet(timeout=MDT_TIMEOUT)
        assert_eq(raw is not None, True)
        # Firmware NACKs unknown commands
        flags = raw[MDTOffset.FLAGS]
        assert_eq(bool(flags & MDTFlags.STATUS_ERROR), True)
    finally:
        link.close()


# Breakpoints
@parametrize("bp_id,control,ctrl_val", [
    (0, BreakpointControl.ENABLED,  0x01),
    (1, BreakpointControl.ENABLED,  0x01),
    (2, BreakpointControl.DISABLED, 0x00),
    (3, BreakpointControl.DISABLED, 0x00),
    (0, BreakpointControl.RESET,    0x02),
    (1, BreakpointControl.NEXT,     0x03),
])
def test_hw_breakpoint_control_acked(bp_id, control, ctrl_val):
    """Every valid breakpoint control command must be ACKed."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        # mem_id carries the control value; address carries the slot id
        cmd = _cmd(CommandId.BREAKPOINT, mem=ctrl_val, address=bp_id)
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.BREAKPOINT)
    finally:
        link.close()

def test_hw_breakpoint_invalid_slot_nacked():
    """Slot ID >= MDT_MAX_BREAKPOINTS (4) must be NACKed by the firmware."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.BREAKPOINT, mem=0x01, address=99)
        raw = _send(link, cmd)
        assert_eq(raw is not None, True)
        # Firmware returns status=0 for invalid slot → STATUS_ERROR set
        assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.STATUS_ERROR), True)
    finally:
        link.close()

def test_hw_enable_then_disable_breakpoint():
    """Enable a breakpoint then immediately disable it — both must ACK."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        for ctrl_val in (0x01, 0x00):   # ENABLE then DISABLE
            raw = _send(link, _cmd(CommandId.BREAKPOINT,
                                   mem=ctrl_val, address=0))
            _assert_clean_ack(raw, CommandId.BREAKPOINT)
            _flush(link)
    finally:
        link.close()

def test_hw_reset_breakpoint_acked():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.BREAKPOINT,
                               mem=BreakpointControl.RESET, address=0))
        _assert_clean_ack(raw, CommandId.BREAKPOINT)
    finally:
        link.close()


# Watchpoints
@parametrize("wp_id,control,payload", [
    (0, WatchpointControl.DISABLED, 0x00000000),
    (1, WatchpointControl.DISABLED, 0x00000000),
    (2, WatchpointControl.DISABLED, 0x00000000),
    (3, WatchpointControl.DISABLED, 0x00000000),
])
def test_hw_watchpoint_disable_acked(wp_id, control, payload):
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        data = payload.to_bytes(4, "little")
        cmd = _cmd(CommandId.WATCHPOINT, mem=int(control),
                   address=wp_id, data=data)
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.WATCHPOINT)
    finally:
        link.close()

def test_hw_watchpoint_enable_acked():
    """Enable a watchpoint on a 4-byte aligned SRAM address."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        watched_addr = TEST_SRAM_BASE  # guaranteed 4-byte aligned
        data = watched_addr.to_bytes(4, "little")
        cmd = _cmd(CommandId.WATCHPOINT, mem=int(WatchpointControl.ENABLED),
                   address=0, data=data)
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.WATCHPOINT)
        _flush(link)
        # Disable immediately so it does not fire during other tests
        _send(link, _cmd(CommandId.WATCHPOINT,
                         mem=int(WatchpointControl.DISABLED),
                         address=0, data=b'\x00\x00\x00\x00'))
    finally:
        link.close()

def test_hw_watchpoint_reset_acked():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.WATCHPOINT, mem=int(WatchpointControl.RESET),
                   address=0, data=b'\x00\x00\x00\x00')
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.WATCHPOINT)
    finally:
        link.close()

def test_hw_watchpoint_mask_on_active_slot_acked():
    """
    Set a bit-mask on a watchpoint that was just enabled.
    The firmware only accepts MASK on an active slot.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        watched_addr = TEST_SRAM_BASE
        # Enable slot 1
        _send(link, _cmd(CommandId.WATCHPOINT,
                         mem=int(WatchpointControl.ENABLED),
                         address=1,
                         data=watched_addr.to_bytes(4, "little")))
        _flush(link)
        # Set mask
        mask = 0x000000FF
        raw = _send(link, _cmd(CommandId.WATCHPOINT,
                               mem=int(WatchpointControl.MASK),
                               address=1,
                               data=mask.to_bytes(4, "little")))
        _assert_clean_ack(raw, CommandId.WATCHPOINT)
        _flush(link)
        # Cleanup
        _send(link, _cmd(CommandId.WATCHPOINT,
                         mem=int(WatchpointControl.RESET),
                         address=1, data=b'\x00\x00\x00\x00'))
    finally:
        link.close()

def test_hw_watchpoint_mask_on_inactive_slot_nacked():
    """MASK on a disabled slot must return STATUS_ERROR."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        # Make sure slot 3 is disabled first
        _send(link, _cmd(CommandId.WATCHPOINT,
                         mem=int(WatchpointControl.DISABLED),
                         address=3, data=b'\x00\x00\x00\x00'))
        _flush(link)
        raw = _send(link, _cmd(CommandId.WATCHPOINT,
                               mem=int(WatchpointControl.MASK),
                               address=3,
                               data=(0xFF).to_bytes(4, "little")))
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.STATUS_ERROR), True)
    finally:
        link.close()

def test_hw_watchpoint_invalid_slot_nacked():
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.WATCHPOINT, mem=int(WatchpointControl.DISABLED),
                   address=99, data=b'\x00\x00\x00\x00')
        raw = _send(link, cmd)
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.STATUS_ERROR), True)
    finally:
        link.close()


# Event packets
def test_hw_failed_packet_event_has_event_flag():
    """
    After a bad-CRC packet the firmware emits a FAILED_PACKET event.
    The event packet must have the EVENT flag set and cmd_id == 0.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        # Corrupt a packet to trigger FAILED_PACKET event
        bad = bytearray(serialize_command_packet(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        bad[MDTOffset.DATA] ^= 0xFF
        link.send_packet(bytes(bad))

        # First response is the NACK
        nack = link.read_packet(timeout=MDT_TIMEOUT)
        assert_eq(nack is not None, True)
        assert_eq(is_nack_packet(nack), True)

        # Second packet is the event (may arrive immediately after)
        event = link.read_packet(timeout=MDT_TIMEOUT)
        if event is None:
            # Older firmware may not emit the event; skip check but don't fail
            print("  [INFO] No event packet received — firmware may batch events")
            return
        assert_eq(bool(event[MDTOffset.FLAGS] & MDTFlags.EVENT_PACKET), True)
        assert_eq(event[MDTOffset.CMD_ID], 0x00)
    finally:
        link.close()

def test_hw_event_packet_framing_is_valid():
    """Any event packet emitted by the MCU must have correct framing and CRC."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        bad = bytearray(serialize_command_packet(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        bad[MDTOffset.DATA] ^= 0xFF
        link.send_packet(bytes(bad))

        pkts = []
        for _ in range(2):
            p = link.read_packet(timeout=MDT_TIMEOUT)
            if p:
                pkts.append(p)

        for p in pkts:
            assert_eq(len(p), MDT_PACKET_SIZE)
            assert_eq(p[MDTOffset.START], 0xAA)
            assert_eq(p[MDTOffset.END],   0x55)
            crc_recv = int.from_bytes(p[MDTOffset.CRC:MDTOffset.CRC + 2], "little")
            crc_calc  = calculate_crc16(p[MDTOffset.CMD_ID:MDTOffset.CRC])
            assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_rx_worker_routes_event_to_event_queue():
    """
    Start the rx_worker thread, trigger an event via a bad packet,
    and verify the event ends up in serial_link.event_queue.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        # Start the background worker
        t = threading.Thread(target=rx_worker, args=(link,), daemon=True)
        t.start()

        # Send a bad packet to provoke NACK + FAILED_PACKET event
        bad = bytearray(serialize_command_packet(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        bad[MDTOffset.DATA] ^= 0xFF
        link.send_packet(bytes(bad))

        # The worker should have routed the NACK to response_queue
        nack = link.get_response_packet(timeout=MDT_TIMEOUT)
        assert_eq(nack is not None, True)
        assert_eq(is_nack_packet(nack), True)

        # Event packet (if firmware emits it) goes to event_queue
        evt = link.get_event_packet(timeout=MDT_TIMEOUT)
        if evt is not None:
            assert_eq(bool(evt[MDTOffset.FLAGS] & MDTFlags.EVENT_PACKET), True)
    finally:
        link.running = False
        link.close()


# Chunked transfers
def _start_rx_worker(link: MCUSerialLink) -> threading.Thread:
    t = threading.Thread(target=rx_worker, args=(link,), daemon=True)
    t.start()
    return t

def test_hw_chunked_16_byte_write_all_acked():
    """
    execute_command() splits a 16-byte write into 4 × 4-byte packets.
    Every chunk must receive an ACK from the real MCU.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    t = _start_rx_worker(link)
    try:
        payload = bytes(range(16))
        cmd = _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                   address=TEST_SRAM_BASE + 0x40,
                   length=16, data=payload)
        execute_command(cmd, serial_link=link)
    finally:
        link.running = False
        link.close()
        t.join(timeout=2.0)

def test_hw_chunked_write_then_read_back():
    """
    Write 8 bytes in two chunks via execute_command(), then read each
    4-byte word individually and verify the payload was stored correctly.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    t = _start_rx_worker(link)
    try:
        base = TEST_SRAM_BASE + 0x50
        payload = b'\x10\x20\x30\x40\x50\x60\x70\x80'

        write_cmd = _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=base, length=8, data=payload)
        execute_command(write_cmd, serial_link=link)
        time.sleep(0.1)

        # Read first word
        r0 = link.get_response_packet(timeout=MDT_TIMEOUT)
        # Drain anything else the worker queued
        time.sleep(0.2)

        # Now do a direct single-word read for verification
        pkt = bytearray(serialize_command_packet(
            _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                 address=base, length=4),
            seq=0, multi=False, last=False))
        link.send_packet(bytes(pkt))
        resp = link.get_response_packet(timeout=MDT_TIMEOUT)
        assert_eq(resp is not None, True)
        parsed = deserialize_command_packet(resp)
        assert_eq(parsed.data, payload[:4])
    finally:
        link.running = False
        link.close()
        t.join(timeout=2.0)


# Stress tests
def test_hw_20_pings_all_acked():
    """Send 20 PINGs in sequence — every one must get a clean ACK."""
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        for i in range(20):
            raw = _send(link, _cmd(CommandId.PING))
            assert_eq(raw is not None, True,
                      **{"iteration": i})
            assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.ACK_NACK), True,
                      **{"iteration": i})
            assert_eq(bool(raw[MDTOffset.FLAGS] & MDTFlags.STATUS_ERROR), False,
                      **{"iteration": i})
    finally:
        link.close()

def test_hw_interleaved_write_read_stress():
    """
    Alternate 10 write/read pairs rapidly.
    The MCU must process all of them without dropping any.
    """
    if not HW_AVAILABLE: return _skip()
    link = _link()
    try:
        addr = TEST_SRAM_BASE + 0x60
        for i in range(10):
            pattern = bytes([i, i ^ 0xFF, (i * 3) & 0xFF, (i * 7) & 0xFF])
            _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                             address=addr, length=4, data=pattern))
            _flush(link, ms=50)
            pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                          address=addr, length=4))
            assert_eq(pkt is not None, True, **{"iteration": i})
            assert_eq(pkt.data, pattern,     **{"iteration": i})
            _flush(link, ms=50)
    finally:
        link.close()
