"""
EMULATED MCU TESTS: the PC tool against the validation firmware running in Renode or simavr

    MDT_SIM=f103c8 python3 -m test.pymdtest simulation       (see emulated_target.py)

The real session, rules, client, link and event pump talk to real firmware over a socket;
test/common/fault_proxy.py sits in between when a test damages the line.

Coverage:
1. Memory: long writes read back at every length and offset; the firmware runs; symbols, local statics
2. Flash: the image reads back and is protected; erase/write above it (where the emulator can)
3. Registers: every register of the UART peripheral reads; AVR 16-bit registers both bytes
4. Watchpoints: changes reported, MASK silences, DISABLED/RESET stop, MASK needs its value, quiet words
5. Breakpoints: the firmware hits one, halts (still serving commands), NEXT steps, DISABLED runs free
6. A damaged line: corrupted CRC or data, dropped, late, noisy, doubled or byte-by-byte replies;
   every reply corrupted; an unplugged cable
7. Load: 240 commands with events flowing; stale events drained at the next start
"""

import time
from functools import cache

from pc_tool import (
    command_client,
    command_parser,
    debug_session,
    event_pump,
    serial_link,
    target_model,
    user_console,
)
from pc_tool.wire_protocol import Command, CommandId, EventType, encode
from test.common import fault_proxy as fp
from test.common.asserts import assert_eq, logged_warnings
from test.simulation import emulated_target as emu

SPECS = command_parser.load_specs()
PING = encode(Command(name="PING", id=CommandId.PING))
HIT = EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT
BREAK = EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT


@cache
def model() -> target_model.Target:
    t = emu.target()
    return target_model.load_target(t.build_info, t.elf)


def sym(name: str) -> int:
    return model().symbols[name].address


class _Console(user_console.Console):
    def __init__(self):
        super().__init__(history_file=emu.temp_dir() / "history")
        self.quiet = True
        self.packets, self.events = [], []

    def packet(self, packet):
        self.packets.append(packet)

    def event(self, event):
        self.events.append((time.monotonic(), event))


class Live:
    """A session on the emulated MCU, through *proxy* when given. Use with `with`."""

    def __init__(self, proxy: fp.FaultProxy | None = None):
        t = emu.target()
        self.console = _Console()
        self.lost = []
        self.link = serial_link.SerialLink(f"socket://localhost:{proxy.port}" if proxy else t.url, reset_delay=0)
        self.link.open()
        assert self.link.sync(PING), "the MCU did not answer the startup ping"
        self.pump = event_pump.EventPump(self.link, t.uart_idle, on_event=self.console.event,
                                         on_lost=lambda: self.lost.append(time.monotonic()))
        self.drained = self.pump.drain_stale_events()
        self.pump.start()
        self.session = debug_session.DebugSession(model(), SPECS, command_client.CommandClient(self.link), self.console)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.pump.stop()
        self.link.close()

    def run(self, line: str):
        start = len(self.console.packets)
        self.session.run_line(line)
        return self.console.packets[start:]

    def ok(self, line: str):
        replies = self.run(line)
        assert replies and all(r.is_ack and not r.is_error for r in replies), (line, replies)
        return replies

    def word(self, line: str) -> int:
        replies = self.ok(line)
        assert_eq(len(replies), 1, line=line)
        return int.from_bytes(replies[0].data, "little")

    def refused(self, line: str, contains: str) -> None:
        try:
            self.run(line)
        except command_parser.CommandError as exc:
            assert contains in str(exc), f"{line!r}: {exc}"
            return
        raise AssertionError(f"{line!r} was accepted")

    def events(self, kind, since=0.0):
        return [e for t, e in self.console.events if e.kind == kind and t >= since]

    def wait_events(self, kind, count=1, timeout=5.0, since=0.0):
        deadline = time.monotonic() + timeout
        while len(self.events(kind, since)) < count and time.monotonic() < deadline:
            time.sleep(0.05)
        return self.events(kind, since)

    def quiet_for(self, kind, seconds: float) -> bool:
        time.sleep(0.6)                                  # a sample already on the wire may still arrive
        since = time.monotonic()
        time.sleep(seconds)
        return not self.events(kind, since)


def _faulted(fault):
    """READ quiet_word with *fault* on the first reply; the session must stay in step after it."""
    proxy = fp.FaultProxy(emu.target().port)
    try:
        with Live(proxy) as live, logged_warnings("pc_tool") as logged:
            proxy.fault = fault
            value = live.word("READ_MEM RAM quiet_word 4")
            proxy.fault = lambda packet: packet
            assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
        return value, list(logged)
    finally:
        proxy.close()


# ---------------------------------------------------------------- 1. memory

def test_long_writes_read_back_at_every_length_and_offset():
    if emu.skip():
        return
    base = sym("scratch")
    pattern = bytes((i * 37 + 11) & 0xFF for i in range(64))
    with Live() as live:
        live.ok(f"WRITE_MEM RAM 0x{base:X} 64 {pattern.hex()}")
        assert_eq(b"".join(r.data for r in live.ok(f"READ_MEM RAM 0x{base:X} 64")), pattern)
        for offset, length in ((1, 1), (3, 2), (5, 3), (7, 5), (13, 7), (0, 13), (50, 14)):
            data = bytes((offset + i) ^ 0xA5 for i in range(length))
            live.ok(f"WRITE_MEM RAM 0x{base + offset:X} {length} {data.hex()}")
            got = b"".join(r.data for r in live.ok(f"READ_MEM RAM 0x{base + offset:X} {length}"))[:length]
            assert_eq(got, data, offset=offset, length=length)
        assert_eq(live.ok(f"READ_MEM RAM 0x{base + 49:X} 1")[0].data[0], pattern[49])    # neighbour untouched


def test_the_firmware_runs_and_quiet_words_stay():
    if emu.skip():
        return
    with Live() as live:
        a = live.word("READ_MEM RAM loop_count 4")
        time.sleep(0.3)
        assert live.word("READ_MEM RAM loop_count 4") != a, "loop_count did not move: the firmware is not running"
        assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)


def test_symbols_and_local_statics():
    if emu.skip():
        return
    static = next(name for name in model().symbols if name.startswith("calls."))
    with Live() as live, logged_warnings("pc_tool") as logged:
        assert_eq(live.ok("READ_MEM RAM calls 4")[0].address, sym(static))
        live.ok("READ_MEM RAM narrow8 1")
    assert any("'narrow8' is uint8_t" in line for line in logged), logged


# ---------------------------------------------------------------- 2. flash

def test_the_image_reads_back_and_is_protected():
    if emu.skip():
        return
    fw = model().firmware
    with Live() as live:
        assert live.ok(f"READ_MEM FLASH 0x{fw.start:X} 4")[0].data != b"\xff" * 4     # vector table / reset jump
        live.refused(f"WRITE_MEM FLASH 0x{fw.start:X} 4 00000000", "overlaps firmware")
        live.refused(f"WRITE_MEM ERASE 0x{fw.start + fw.size - 1:X} 1 00", "overlaps firmware")


def test_erase_and_write_above_the_image():
    if emu.skip():
        return
    if not emu.target().flash:
        print("  [SKIP] no flash writes on this platform")
        return
    fw = model().firmware
    free = (fw.start + fw.size + fw.page - 1) & ~(fw.page - 1)
    with Live() as live:
        if live.run(f"WRITE_MEM ERASE 0x{free:X} 1 00")[0].is_error:
            print("  [SKIP] the MCU reports the erase failed: Renode models no flash controller for this part")
            return
        assert_eq(live.ok(f"READ_MEM FLASH 0x{free:X} 4")[0].data, b"\xff" * 4)
        live.ok(f"WRITE_MEM FLASH 0x{free:X} 4 CAFEBABE")
        assert_eq(live.ok(f"READ_MEM FLASH 0x{free:X} 4")[0].data, bytes.fromhex("CAFEBABE"))


# ---------------------------------------------------------------- 3. registers

def test_every_uart_register_reads():
    if emu.skip():
        return
    name = "USART" if emu.target().name == "atmega328p" else "USART1"
    peripheral = next(p for p in model().peripherals if p.name == name)
    with Live() as live:
        for register in peripheral.registers:
            if register.name not in ("UDR0", "DR", "RDR"):     # reading the data register takes a byte from the MCU
                live.ok(f"READ_REG {peripheral.name}_{register.name}")


def test_avr_16_bit_register_both_bytes():
    if emu.skip() or emu.target().name != "atmega328p":
        return
    with Live() as live:
        low, high = live.ok("READ_REG 0xC4")[0], live.ok("READ_REG 0xC5")[0]
    assert (low.data[0] | high.data[0] << 8) in (51, 103, 207), (low, high)      # UBRR0 for 19200 baud at 16 MHz


# ---------------------------------------------------------------- 4. watchpoints

def test_watchpoint_reports_masks_disables_and_resets():
    if emu.skip():
        return
    with Live() as live:
        live.ok("WATCHPOINT 0 ENABLED loop_count")
        hits = live.wait_events(HIT, 2)
        assert len(hits) >= 2 and all(h.slot == 0 and h.address != h.data for h in hits), hits
        live.ok("WATCHPOINT 0 MASK 00000000")
        assert live.quiet_for(HIT, 1.5), "events with mask 0"
        live.ok("WATCHPOINT 0 MASK FFFFFFFF")
        assert live.wait_events(HIT, 1, since=time.monotonic()), "no events after unmasking"
        live.ok("WATCHPOINT 0 DISABLED")
        assert live.quiet_for(HIT, 1.5), "events after DISABLED"
        live.ok("WATCHPOINT 0 RESET")


def test_watchpoint_mask_needs_its_value():
    if emu.skip():
        return
    with Live() as live:
        live.ok("WATCHPOINT 0 ENABLED quiet_word")
        try:
            live.refused("WATCHPOINT 0 MASK", "WATCHPOINT MASK needs the mask")
        finally:
            live.run("WATCHPOINT 0 RESET")


def test_watchpoint_on_a_quiet_word_fires_once_per_write():
    if emu.skip():
        return
    with Live() as live:
        live.ok("WATCHPOINT 1 ENABLED quiet_word")
        try:
            assert live.quiet_for(HIT, 1.0), "a quiet word fired"
            since = time.monotonic()
            live.ok("WRITE_MEM RAM quiet_word 4 55667788")
            hits = live.wait_events(HIT, 1, since=since)
            assert hits and (hits[-1].address, hits[-1].data) == (0x11223344, 0x88776655), hits
        finally:
            live.run("WRITE_MEM RAM quiet_word 4 44332211")
            live.run("WATCHPOINT 1 RESET")


def test_watchpoint_on_a_register():
    if emu.skip():
        return
    # the MCU samples 4 bytes: they must not reach a register that changes when read (UBRR0's 4 hold UDR0)
    register = "OCR0A" if emu.target().name == "atmega328p" else "USART1_BRR"
    with Live() as live:
        try:
            live.ok(f"WATCHPOINT 2 ENABLED 0x{model().registers.by_name(register).address:X}")
            assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
        finally:
            live.run("WATCHPOINT 2 RESET")


# ---------------------------------------------------------------- 5. breakpoints

def test_breakpoint_halts_next_steps_disabled_runs_free():
    if emu.skip():
        return
    with Live() as live:
        try:
            live.ok("BREAKPOINT 0 ENABLED")
            hits = live.wait_events(BREAK, 1, timeout=8)
            assert hits, f"no breakpoint hit: {live.console.events[-3:]}"
            a = live.word("READ_MEM RAM slow_count 4")
            time.sleep(0.8)
            assert_eq(live.word("READ_MEM RAM slow_count 4"), a, what="slow_count while halted")
            live.ok("WRITE_MEM RAM scratch 4 01020304")                  # still serving commands while halted
            since = time.monotonic()
            live.ok("BREAKPOINT 0 NEXT")
            step = live.wait_events(BREAK, 1, timeout=8, since=since)
            assert step and step[-1].data == hits[0].data + 1, (hits, step)
            assert_eq(live.word("READ_MEM RAM slow_count 4"), a + 1)
            live.ok("BREAKPOINT 0 DISABLED")
            c = live.word("READ_MEM RAM slow_count 4")
            time.sleep(1.0)
            assert live.word("READ_MEM RAM slow_count 4") != c, "slow_count stuck after DISABLED"
        finally:
            live.run("BREAKPOINT 0 RESET")


# ---------------------------------------------------------------- 6. a damaged line

def test_corrupted_crc_is_resent():
    if emu.skip():
        return
    value, logged = _faulted(fp.nth_reply(1, fp.flip_crc))
    assert_eq(value, 0x11223344)
    assert any("corrupted packet" in line for line in logged), logged


def test_corrupted_data_is_caught_by_the_crc():
    if emu.skip():
        return
    assert_eq(_faulted(fp.nth_reply(1, fp.flip_data))[0], 0x11223344)


def test_dropped_reply_is_resent():
    if emu.skip():
        return
    value, logged = _faulted(fp.nth_reply(1, fp.drop))
    assert_eq(value, 0x11223344)
    assert any("No response from MCU for seq=0 (attempt 1/3)" in line for line in logged), logged


def test_noise_and_a_false_start_byte_resync():
    if emu.skip():
        return
    assert_eq(_faulted(fp.nth_reply(1, fp.with_noise))[0], 0x11223344)


def test_late_reply_does_not_desync_the_next_commands():
    if emu.skip():
        return
    proxy = fp.FaultProxy(emu.target().port)
    try:
        with Live(proxy) as live:
            proxy.fault = fp.nth_reply(1, fp.delayed(1.4))
            live.ok("READ_MEM RAM quiet_word 4")
            proxy.fault = lambda packet: packet
            for _ in range(5):
                assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
            live.ok(f"WRITE_MEM RAM 0x{sym('scratch'):X} 4 0BADF00D")
            assert_eq(live.word(f"READ_MEM RAM 0x{sym('scratch'):X} 4"), 0x0DF0AD0B)
    finally:
        proxy.close()


def test_doubled_and_byte_by_byte_replies():
    if emu.skip():
        return
    proxy = fp.FaultProxy(emu.target().port)
    try:
        with Live(proxy) as live:
            proxy.fault = fp.doubled
            for _ in range(3):
                assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
            proxy.fault = lambda packet: packet
            proxy.split_delay = 0.003
            assert_eq(len(live.ok(f"READ_MEM RAM 0x{sym('scratch'):X} 12")), 3)
            assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
    finally:
        proxy.close()


def test_every_reply_corrupted_is_a_no_reply_error_then_recovers():
    if emu.skip():
        return
    proxy = fp.FaultProxy(emu.target().port)
    try:
        with Live(proxy) as live:
            proxy.fault = lambda packet: fp.flip_crc(packet) if fp.is_reply(packet) else packet
            try:
                live.run("READ_MEM RAM quiet_word 4")
            except command_client.NoReplyError as exc:
                assert "after 3 attempts" in str(exc), exc
            else:
                raise AssertionError("no NoReplyError")
            proxy.fault = lambda packet: packet
            assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
    finally:
        proxy.close()


def test_unplugged_cable_reports_the_link_lost():
    if emu.skip():
        return
    proxy = fp.FaultProxy(emu.target().port)
    try:
        with Live(proxy) as live:
            assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
            unplugged = time.monotonic()
            proxy.unplug()
            while not live.lost and time.monotonic() < unplugged + 3:
                time.sleep(0.02)
            assert live.lost and live.lost[0] - unplugged < 1.0, live.lost
            assert_eq(live.pump.lost, True)
    finally:
        proxy.close()


# ---------------------------------------------------------------- 7. load

def test_240_commands_with_events_flowing():
    if emu.skip():
        return
    base = sym("scratch")
    with Live() as live, logged_warnings("pc_tool") as logged:
        live.ok("WATCHPOINT 3 ENABLED loop_count")                       # an event on every sample
        try:
            for i in range(120):
                data = bytes(((i + k) * 29) & 0xFF for k in range(8))
                live.ok(f"WRITE_MEM RAM 0x{base:X} 8 {data.hex()}")
                assert_eq(b"".join(r.data for r in live.ok(f"READ_MEM RAM 0x{base:X} 8")), data, i=i)
        finally:
            live.run("WATCHPOINT 3 RESET")
        assert live.events(HIT), "no events during the run"
    assert not [line for line in logged if "No response" in line], logged[:3]


def test_stale_events_are_drained_at_the_next_start():
    if emu.skip():
        return
    with Live() as live:
        live.ok("WATCHPOINT 0 ENABLED loop_count")
        time.sleep(1.0)
    with Live() as live:                                                   # events left pending by the last session
        live.ok("WATCHPOINT 0 RESET")
        assert_eq(live.word("READ_MEM RAM quiet_word 4"), 0x11223344)
