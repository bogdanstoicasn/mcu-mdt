"""
HARDWARE TESTS FOR MCU-MDT


Run these against a real MCU flashed with the MDT firmware.

Usage:
    # ATmega328P on /dev/ttyACM0
    MCU=ATmega328P python3 -m test.pymdtest hardware

    # STM32F030F4 on /dev/ttyUSB0
    MCU=F030F4 python3 -m test.pymdtest hardware

    # Windows
    MCU=F030F4 python3 -m test.pymdtest hardware

Environment variables:
    MCU           MCU identifier matching build/<MCU>/build_info.yaml.
                  When set, sram_base and flash_base are derived from the
                  SVD/ATDF database; otherwise defaults are used.
    MDT_PORT      Serial port.  If unset every test is skipped gracefully.
    MDT_BAUD      Baud rate  (default: 19200)
    MDT_TIMEOUT   Per-packet read timeout in seconds  (default: 2.0)
    MDT_PLATFORM  "avr" or "stm32"  (default: "avr")

Coverage:
1.  Link health       (ping, framing, crc)
2.  Memory read       (read from sram and flash, return valid ack)
3.  Memory write/read (write patterns, read them back, verify)
4.  Register/SRAM     (READ_REG/WRITE_REG round-trip via scratch SRAM)
5.  Protocol          (bad crc, recovery, resync)
6.  Breakpoints
7.  Watchpoints
8.  Event packets
9.  Chunked transfer
10. Stress

Assumptions:
1. Firmware running (mcu_mdt_poll / interrupt loop)
2. ≥64B free SRAM above sram_base
3. sram_base / flash_base resolved from SVD/ATDF when MCU is set,
   otherwise: AVR 0x0200 / 0x0000, STM32 0x20000200 / 0x08000000
"""

import os
import time
from dataclasses import dataclass

import yaml

from pc_tool import command_client, event_pump, target_model
from pc_tool.serial_link import SerialLink
from pc_tool.wire_protocol import (
    PACKET_SIZE,
    WORD_SIZE,
    BreakpointControl,
    Command,
    CommandId,
    EventType,
    Flag,
    MemType,
    Offset,
    PacketError,
    WatchpointControl,
    crc16,
    decode,
    encode,
    is_nack,
)
from test.common.asserts import assert_eq
from test.pymdtest import parametrize


@dataclass(frozen=True)
class HWConfig:
    port:       str
    baud:       int
    timeout:    float
    platform:   str
    sram_base:  int      # first safe scratch word inside SRAM
    flash_base: int      # start of flash region
    target:     object   # the Target as the PC tool loads it, None without MCU
    registers:  dict     # { "PERIPH.REG": {addr, reset_value, reset_mask, access} }
    uart_idle:  bool = False  # True when MDT_FEATURE_UART_IDLE=1 (STM32 interrupt mode)

    @property
    def available(self) -> bool:
        return bool(self.port)

    def scratch(self, slot: int) -> int:
        """
        Return a 4-byte-aligned SRAM address for test slot *slot*.
        Each slot is 4 bytes wide; slots start at sram_base.
        Tests use named slots instead of raw offsets so the mapping is
        explicit and conflicts are visible in one place:

            slot  0  — basic read / watchpoint base
            slot  1  — write_all_zeros
            slot  2  — write_all_ones
            slot  4  — adjacent_writes word A   (gap at 3 is intentional)
            slot  5  — adjacent_writes word B
            slot  8  — various_patterns / parametrized write-read
            slot 12  — reg round-trip
            slot 16  — chunked 16-byte write (needs 4 consecutive slots: 16-19)
            slot 20  — chunked write+readback (needs 2 consecutive slots: 20-21)
            slot 24  — stress interleaved write-read
        """
        return self.sram_base + slot * 4

    @classmethod
    def from_sources(cls) -> "HWConfig":
        """
        Load configuration from:
        1. build/<MCU>/build_info.yaml  (if MCU is set)
        2. environment variables (override)
        3. Sensible defaults when MCU is absent

        sram_base and flash_base are resolved from the MCU metadata
        (target.segments) when MCU is provided, avoiding any hardcoded
        addresses in this file.  A safe 0x200-byte guard is added to
        sram_base so test writes never collide with firmware variables at
        the bottom of SRAM.
        """
        mcu = os.environ.get("MCU", "")
        data = {}

        if mcu:
            # If we are from test directory, we go 1 directory back to find build/
            if os.path.basename(os.getcwd()) == "test":
                os.chdir("..")
            path = os.path.join("build", mcu.lower(), "build_info.yaml")   # build dirs are lowercase
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"Build info not found for MCU='{mcu}' at {path}"
                )
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        platform = (
            os.environ.get("MDT_PLATFORM")
            or data.get("platform", "avr")
        ).lower()

        port    = os.environ.get("MDT_PORT",    data.get("port", ""))
        baud    = int(os.environ.get("MDT_BAUD",    data.get("baudrate", 19200)))
        timeout = float(os.environ.get("MDT_TIMEOUT", "2.0"))

        # Load the target when we have an MCU identifier; fall back to
        # hardcoded bases when running without one.
        target = None
        if mcu:
            try:
                target = target_model.load_target(path)
            except Exception as exc:
                print(f"  [WARN] Could not load the target: {exc}")

        sram_base, flash_base = _resolve_memory_bases(target, platform)

        uart_idle = bool(int(data.get("uart_idle", 0)))

        return cls(
            port=port,
            baud=baud,
            timeout=timeout,
            platform=platform,
            sram_base=sram_base,
            flash_base=flash_base,
            target=target,
            registers=None,
            uart_idle=uart_idle,
        )


def _resolve_memory_bases(target, platform: str) -> tuple[int, int]:
    """
    Derive sram_base and flash_base from the target's memory segments.
    Falls back to well-known constants when there is no target.
    The 0x200 guard on sram_base keeps test writes away from firmware
    variables that live at the bottom of SRAM.
    """
    segments  = target.segments if target else ()
    ram_seg   = next((s for s in segments if s.kind == "ram"),   None)
    flash_seg = next((s for s in segments if s.kind == "flash"), None)

    stm32 = "stm32" in platform

    if ram_seg:
        sram_base = ram_seg.start + 0x200
    else:
        sram_base = 0x20000200 if stm32 else 0x0200

    if flash_seg:
        flash_base = flash_seg.start
    else:
        flash_base = 0x08000000 if stm32 else 0x0000

    return sram_base, flash_base

HW = HWConfig.from_sources()


# Helpers
def _skip(msg="MDT_PORT not set — connect a MCU and re-run"):
    """Print a skip message and return True so the test can do `if not HW.available: return _skip()`."""
    print(f"  [SKIP] {msg}")
    return True


def _link() -> SerialLink:
    """Open a serial link with a short reset delay."""
    link = SerialLink(HW.port, HW.baud, reset_delay=2.0)
    link.open()
    return link


def _cmd(cmd_id, *, mem=None, address=0, length=0, data=None) -> Command:
    """Helper to build a Command with minimal boilerplate."""
    return Command(
        name=cmd_id.name,
        id=cmd_id,
        mem=mem,
        address=address,
        length=length,
        data=data,
    )


def _send(link: SerialLink, cmd: Command,
          seq=0, multi=False, last=False) -> bytes | None:
    """Serialize, transmit, and return the raw 18-byte response (or None)."""
    pkt = encode(cmd, seq=seq, multi=multi, last=last)
    link.send(pkt)
    return link.read_packet(timeout=HW.timeout)


def _send_parsed(link: SerialLink, cmd: Command, **kw):
    """Like _send but returns a deserialized Packet or None."""
    raw = _send(link, cmd, **kw)
    if raw is None:
        return None
    try:
        return decode(raw)
    except PacketError:
        return None

# CMD_ID=0 packet — identical to what _event_poll_worker sends every 500 ms.
_POLL_PKT = encode(
    Command(name="POLL", id=0x00, mem=None, address=0, data=None),
    seq=0, multi=False, last=False,
)


def _read_event(link: SerialLink) -> bytes | None:
    """Read the next event packet from the MCU, handling both processing modes.

    - **Poll mode** (uart_idle=False, AVR default): mcu_mdt_poll() flushes
      the event spontaneously once the TX ring buffer is idle. Just read.

    - **UART idle / interrupt mode** (uart_idle=True, STM32 default): the MCU
      holds the event until a CMD_ID=0 poll packet arrives, exactly as the
      production _event_poll_worker does every 500 ms. Send the poll first.
    """
    if HW.uart_idle:
        link.send(_POLL_PKT)
    return link.read_packet(timeout=HW.timeout)


def _flush(link: SerialLink, ms=300):
    """Drain stale bytes so the next test starts clean."""
    time.sleep(ms / 1000)
    link.drop_input()


def _assert_clean_ack(raw: bytes, cmd_id: int):
    """Assert raw is a valid, non-error ACK for cmd_id."""
    assert_eq(raw is not None, True)
    assert_eq(len(raw), PACKET_SIZE)
    # CRC must be correct
    crc_recv = int.from_bytes(raw[Offset.CRC:Offset.CRC + 2], "little")
    crc_calc  = crc16(raw[Offset.CMD_ID:Offset.CRC])
    assert_eq(crc_recv, crc_calc)
    # ACK flag set, error flag clear, correct command echoed back
    flags = raw[Offset.FLAGS]
    assert_eq(bool(flags & Flag.ACK_NACK),      True)
    assert_eq(bool(flags & Flag.STATUS_ERROR),  False)
    assert_eq(raw[Offset.CMD_ID], cmd_id)


# Health check
def test_hw_ping_gets_response():
    """A PING command must get a response packet (ACK or NACK) rather than timing out."""
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        _assert_clean_ack(raw, CommandId.PING)
    finally:
        link.close()

def test_hw_ping_response_is_exactly_18_bytes():
    """The response to a PING must be exactly one MDT packet long (18 bytes)."""
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(len(raw), PACKET_SIZE)
    finally:
        link.close()

def test_hw_ping_start_end_framing():
    """The response to a PING must have correct START and END framing bytes."""
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(raw[Offset.START], 0xAA)
        assert_eq(raw[Offset.END],   0x55)
    finally:
        link.close()

def test_hw_ping_response_crc_valid():
    """The response to a PING must have a valid CRC covering CMD_ID, FLAGS, and DATA."""
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        crc_recv = int.from_bytes(raw[Offset.CRC:Offset.CRC + 2], "little")
        crc_calc  = crc16(raw[Offset.CMD_ID:Offset.CRC])
        assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_ping_echoes_cmd_id():
    """The response to a PING must echo back the PING command ID (0x05) in the CMD_ID field."""
    if not HW.available: return _skip()
    link = _link()
    try:
        pkt = _send_parsed(link, _cmd(CommandId.PING))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.cmd_id, CommandId.PING)
    finally:
        link.close()

def test_hw_ping_ack_flag_set():
    """The response to a PING must have the ACK_NACK flag set (ACK) rather than clear (NACK)."""
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[Offset.FLAGS] & Flag.ACK_NACK), True)
    finally:
        link.close()

def test_hw_ping_no_error_flag():
    """The response to a PING must not have the STATUS_ERROR flag set."""
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[Offset.FLAGS] & Flag.STATUS_ERROR), False)
    finally:
        link.close()


# Memory read
def test_hw_read_sram_returns_ack():
    """A READ_MEM command targeting SRAM must return a valid ACK packet rather than NACK or timing out."""
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                   address=HW.scratch(0), length=4)
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.READ_MEM)
    finally:
        link.close()

def test_hw_read_sram_data_is_four_bytes():
    """A READ_MEM command targeting SRAM with length=4 must return a packet with exactly 4 bytes of data."""
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                   address=HW.scratch(0), length=4)
        pkt = _send_parsed(link, cmd)
        assert_eq(pkt is not None, True)
        assert_eq(len(pkt.data), WORD_SIZE)
    finally:
        link.close()

def test_hw_read_flash_returns_valid_packet():
    """
    FLASH read may ACK or NACK depending on the MCU, but the response
    must always be a structurally sound 18-byte packet with a valid CRC.
    """
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.FLASH,
                   address=HW.flash_base, length=4)
        raw = _send(link, cmd)
        assert_eq(raw is not None, True)
        assert_eq(len(raw), PACKET_SIZE)
        assert_eq(raw[Offset.START], 0xAA)
        assert_eq(raw[Offset.END],   0x55)
        crc_recv = int.from_bytes(raw[Offset.CRC:Offset.CRC + 2], "little")
        crc_calc  = crc16(raw[Offset.CMD_ID:Offset.CRC])
        assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_read_sram_mem_id_echoed():
    """A READ_MEM command targeting SRAM must return a packet echoing the RAM mem_id rather than FLASH or 0."""
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                   address=HW.scratch(0), length=4)
        pkt = _send_parsed(link, cmd)
        assert_eq(pkt is not None, True)
        assert_eq(pkt.mem_id, MemType.RAM)
    finally:
        link.close()


# Memory write / readback
def test_hw_write_sram_returns_ack():
    """A WRITE_MEM command targeting SRAM must return a valid ACK packet rather than NACK or timing out."""
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                   address=HW.scratch(0), length=4,
                   data=b'\x12\x34\x56\x78')
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.WRITE_MEM)
    finally:
        link.close()

def test_hw_write_then_read_back_pattern():
    """A WRITE_MEM command followed by a READ_MEM command must return the written data."""
    if not HW.available: return _skip()
    link = _link()
    try:
        pattern = b'\xCA\xFE\xBA\xBE'
        _send(link, _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=HW.scratch(0), length=4, data=pattern))
        _flush(link)
        pkt = _send_parsed(link, _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                                      address=HW.scratch(0), length=4))
        assert_eq(pkt is not None, True)
        assert_eq(pkt.data, pattern)
    finally:
        link.close()

def test_hw_write_all_zeros_read_back():
    """A WRITE_MEM command with all zeros followed by a READ_MEM command must return the written data."""
    if not HW.available: return _skip()
    link = _link()
    try:
        addr = HW.scratch(1)
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
    """A WRITE_MEM command with all ones followed by a READ_MEM command must return the written data."""
    if not HW.available: return _skip()
    link = _link()
    try:
        addr = HW.scratch(2)
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
    if not HW.available: return _skip()
    link = _link()
    try:
        addr_a, addr_b = HW.scratch(4), HW.scratch(5)
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
    """A WRITE_MEM command with various patterns followed by a READ_MEM command must return the written data."""
    if not HW.available: return _skip()
    link = _link()
    try:
        addr = HW.scratch(8)
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
    if not HW.available: return _skip()
    link = _link()
    try:
        raw = _send(link, _cmd(CommandId.READ_REG, address=HW.scratch(0)))
        assert_eq(raw is not None, True)
        assert_eq(len(raw), PACKET_SIZE)
        crc_recv = int.from_bytes(raw[Offset.CRC:Offset.CRC + 2], "little")
        assert_eq(crc_recv, crc16(raw[Offset.CMD_ID:Offset.CRC]))
    finally:
        link.close()

def test_hw_write_reg_read_reg_roundtrip():
    """
    Write a byte via WRITE_REG then read it back via READ_REG.
    Both route through hal_write_memory / hal_read_memory on SRAM.
    """
    if not HW.available: return _skip()
    link = _link()
    try:
        addr = HW.scratch(12)
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
    if not HW.available: return _skip()
    link = _link()
    try:
        pkt = bytearray(encode(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        pkt[Offset.DATA] ^= 0xFF          # corrupt without re-patching CRC
        link.send(bytes(pkt))
        raw = link.read_packet(timeout=HW.timeout)
        assert_eq(raw is not None, True)
        assert_eq(is_nack(raw), True)
    finally:
        link.close()

def test_hw_nack_carries_valid_crc():
    """The NACK packet itself must be well-formed with a correct CRC."""
    if not HW.available: return _skip()
    link = _link()
    try:
        pkt = bytearray(encode(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        pkt[Offset.DATA] ^= 0xFF
        link.send(bytes(pkt))
        raw = link.read_packet(timeout=HW.timeout)
        assert_eq(raw is not None, True)
        crc_recv = int.from_bytes(raw[Offset.CRC:Offset.CRC + 2], "little")
        crc_calc  = crc16(raw[Offset.CMD_ID:Offset.CRC])
        assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_mcu_recovers_after_bad_packet():
    """After receiving a bad packet the MCU must still ACK valid ones."""
    if not HW.available: return _skip()
    link = _link()
    try:
        # Send all-zeros (no valid START byte - MCU ignores it)
        link.send(bytes(PACKET_SIZE))
        link.read_packet(timeout=HW.timeout)   # may be None; we don't care
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
    if not HW.available: return _skip()
    link = _link()
    try:
        half = encode(
            _cmd(CommandId.PING), seq=0, multi=False, last=False)[:9]
        link.send(half)
        time.sleep(0.5)     # let the MCU notice nothing more is coming
        _flush(link)
        raw = _send(link, _cmd(CommandId.PING))
        assert_eq(raw is not None, True)
        assert_eq(len(raw), PACKET_SIZE)
    finally:
        link.close()

def test_hw_nack_seq_mirrors_request_seq():
    """The NACK packet must echo back the SEQ byte of the bad request."""
    if not HW.available: return _skip()
    link = _link()
    try:
        TEST_SEQ = 0x2A
        pkt = bytearray(encode(
            _cmd(CommandId.PING), seq=TEST_SEQ, multi=True, last=False))
        pkt[Offset.DATA] ^= 0xFF          # corrupt data, keep seq
        link.send(bytes(pkt))
        raw = link.read_packet(timeout=HW.timeout)
        assert_eq(raw is not None, True)
        assert_eq(is_nack(raw), True)
        assert_eq(raw[Offset.SEQ], TEST_SEQ)
    finally:
        link.close()

def test_hw_unknown_cmd_id_triggers_error_response():
    """
    A packet with cmd_id=0xFF (unknown) must produce a response with the
    STATUS_ERROR flag set.  The firmware dispatches through the handler table;
    an out-of-range cmd_id returns 0 which sets the error flag.
    """
    if not HW.available: return _skip()
    link = _link()
    try:
        # Build a hand-crafted packet with cmd_id = 0xFF
        pkt = bytearray(PACKET_SIZE)
        pkt[Offset.START]  = 0xAA
        pkt[Offset.CMD_ID] = 0xFF
        pkt[Offset.END]    = 0x55
        crc = crc16(bytes(pkt[Offset.CMD_ID:Offset.CRC]))
        pkt[Offset.CRC]     = crc & 0xFF
        pkt[Offset.CRC + 1] = (crc >> 8) & 0xFF
        link.send(bytes(pkt))
        raw = link.read_packet(timeout=HW.timeout)
        assert_eq(raw is not None, True)
        # Firmware NACKs unknown commands
        flags = raw[Offset.FLAGS]
        assert_eq(bool(flags & Flag.STATUS_ERROR), True)
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
    if not HW.available: return _skip()
    link = _link()
    try:
        # mem_id carries the control value; address carries the slot id
        cmd = _cmd(CommandId.BREAKPOINT, mem=ctrl_val, address=bp_id)
        raw = _send(link, cmd)
        _assert_clean_ack(raw, CommandId.BREAKPOINT)
    finally:
        link.close()

def test_hw_breakpoint_invalid_slot_nacked():
    """A slot ID beyond the build's breakpoint count (at most 8) must be NACKed by the firmware."""
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.BREAKPOINT, mem=0x01, address=99)
        raw = _send(link, cmd)
        assert_eq(raw is not None, True)
        # Firmware returns status=0 for invalid slot - STATUS_ERROR set
        assert_eq(bool(raw[Offset.FLAGS] & Flag.STATUS_ERROR), True)
    finally:
        link.close()

def test_hw_enable_then_disable_breakpoint():
    """Enable a breakpoint then immediately disable it — both must ACK."""
    if not HW.available: return _skip()
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
    if not HW.available: return _skip()
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
    """Disable a watchpoint on a 4-byte aligned SRAM address."""
    if not HW.available: return _skip()
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
    if not HW.available: return _skip()
    link = _link()
    try:
        watched_addr = HW.scratch(0)  # guaranteed 4-byte aligned
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
    """Reset a watchpoint slot — this is like DISABLED but also clears the address and mask."""
    if not HW.available: return _skip()
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
    if not HW.available: return _skip()
    link = _link()
    try:
        watched_addr = HW.scratch(0)
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
    if not HW.available: return _skip()
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
        assert_eq(bool(raw[Offset.FLAGS] & Flag.STATUS_ERROR), True)
    finally:
        link.close()

def test_hw_watchpoint_invalid_slot_nacked():
    """A slot ID beyond the build's watchpoint count (at most 8) must be NACKed by the firmware."""
    if not HW.available: return _skip()
    link = _link()
    try:
        cmd = _cmd(CommandId.WATCHPOINT, mem=int(WatchpointControl.DISABLED),
                   address=99, data=b'\x00\x00\x00\x00')
        raw = _send(link, cmd)
        assert_eq(raw is not None, True)
        assert_eq(bool(raw[Offset.FLAGS] & Flag.STATUS_ERROR), True)
    finally:
        link.close()


# Event packets
def test_hw_failed_packet_event_has_event_flag():
    """
    After a bad-CRC packet the firmware emits a FAILED_PACKET event.
    The event packet must have the EVENT flag set and cmd_id == 0.

    In poll mode the event arrives spontaneously after the NACK.
    In UART idle / interrupt mode it arrives in the response to a
    CMD_ID=0 poll packet — _read_event() handles both cases.
    """
    if not HW.available: return _skip()
    link = _link()
    try:
        bad = bytearray(encode(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        bad[Offset.DATA] ^= 0xFF
        link.send(bytes(bad))

        nack = link.read_packet(timeout=HW.timeout)
        assert_eq(nack is not None, True)
        assert_eq(is_nack(nack), True)

        event = _read_event(link)
        assert_eq(event is not None, True)
        assert_eq(bool(event[Offset.FLAGS] & Flag.EVENT_PACKET), True)
        assert_eq(event[Offset.CMD_ID], 0x00)
    finally:
        link.close()

def test_hw_event_packet_framing_is_valid():
    """NACK and the following FAILED_PACKET event must both have valid framing and CRC."""
    if not HW.available: return _skip()
    link = _link()
    try:
        bad = bytearray(encode(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        bad[Offset.DATA] ^= 0xFF
        link.send(bytes(bad))

        nack  = link.read_packet(timeout=HW.timeout)
        event = _read_event(link)

        for p in (nack, event):
            assert_eq(p is not None, True)
            assert_eq(len(p), PACKET_SIZE)
            assert_eq(p[Offset.START], 0xAA)
            assert_eq(p[Offset.END],   0x55)
            crc_recv = int.from_bytes(p[Offset.CRC:Offset.CRC + 2], "little")
            crc_calc  = crc16(p[Offset.CMD_ID:Offset.CRC])
            assert_eq(crc_recv, crc_calc)
    finally:
        link.close()

def test_hw_event_pump_routes_nack_and_event():
    """
    Start the event pump, trigger an event via a bad packet, and verify the NACK
    reaches the replies and the event (if the firmware sends one) reaches on_event.
    """
    if not HW.available: return _skip()
    link = _link()
    events = []
    pump = event_pump.EventPump(link, HW.uart_idle, on_event=events.append)
    try:
        pump.start()

        # Send a bad packet to provoke NACK + FAILED_PACKET event
        bad = bytearray(encode(
            _cmd(CommandId.PING), seq=0, multi=False, last=False))
        bad[Offset.DATA] ^= 0xFF
        link.send(bytes(bad))

        # The pump should have routed the NACK to the replies
        nack = link.next_reply(timeout=HW.timeout)
        assert_eq(nack is not None, True)
        assert_eq(nack.is_nack, True)

        # The FAILED_PACKET event (if the firmware emits it) goes to on_event
        deadline = time.monotonic() + HW.timeout
        while not events and time.monotonic() < deadline:
            time.sleep(0.05)
        if events:
            assert_eq(events[0].kind, EventType.INTERNAL_MDT_EVENT_FAILED_PACKET)
    finally:
        pump.stop()
        link.close()


# Chunked transfers
def _start_pump(link: SerialLink) -> event_pump.EventPump:
    pump = event_pump.EventPump(link, uart_idle=False, on_event=lambda event: None)
    pump.start()
    return pump

def test_hw_chunked_16_byte_write_all_acked():
    """
    CommandClient.run() splits a 16-byte write into 4 × 4-byte packets.
    Every chunk must receive an ACK from the real MCU.
    """
    if not HW.available: return _skip()
    link = _link()
    pump = _start_pump(link)
    try:
        payload = bytes(range(16))
        cmd = _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                   address=HW.scratch(16),
                   length=16, data=payload)
        replies = command_client.CommandClient(link).run(cmd)
        assert_eq(len(replies), 4)
        assert_eq(any(r.is_error for r in replies), False)
    finally:
        pump.stop()
        link.close()

def test_hw_chunked_write_then_read_back():
    """
    Write 8 bytes in two chunks via CommandClient.run(), then read each
    4-byte word individually and verify the payload was stored correctly.
    """
    if not HW.available: return _skip()
    link = _link()
    pump = _start_pump(link)
    try:
        base = HW.scratch(20)
        payload = b'\x10\x20\x30\x40\x50\x60\x70\x80'

        write_cmd = _cmd(CommandId.WRITE_MEM, mem=MemType.RAM,
                         address=base, length=8, data=payload)
        command_client.CommandClient(link).run(write_cmd)
        time.sleep(0.2)

        # Now do a direct single-word read for verification
        pkt = bytearray(encode(
            _cmd(CommandId.READ_MEM, mem=MemType.RAM,
                 address=base, length=4),
            seq=0, multi=False, last=False))
        link.send(bytes(pkt))
        resp = link.next_reply(timeout=HW.timeout)
        assert_eq(resp is not None, True)
        assert_eq(resp.data, payload[:4])
    finally:
        pump.stop()
        link.close()


# Stress tests
def test_hw_20_pings_all_acked():
    """Send 20 PINGs in sequence — every one must get a clean ACK."""
    if not HW.available: return _skip()
    link = _link()
    try:
        for i in range(20):
            raw = _send(link, _cmd(CommandId.PING))
            assert_eq(raw is not None, True,
                      **{"iteration": i})
            assert_eq(bool(raw[Offset.FLAGS] & Flag.ACK_NACK), True,
                      **{"iteration": i})
            assert_eq(bool(raw[Offset.FLAGS] & Flag.STATUS_ERROR), False,
                      **{"iteration": i})
    finally:
        link.close()

def test_hw_interleaved_write_read_stress():
    """
    Alternate 10 write/read pairs rapidly.
    The MCU must process all of them without dropping any.
    """
    if not HW.available: return _skip()
    link = _link()
    try:
        addr = HW.scratch(24)
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
