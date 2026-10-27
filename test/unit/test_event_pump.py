"""
EVENT PUMP TESTS (pc_tool/event_pump.py), on an in-process fake MCU

Coverage:
1. Routing: events to on_event, empty poll answers dropped, everything else a reply
2. A corrupted packet is dropped with a warning; the reader goes on
3. UART-idle mode polls for events on its own, and again right after each event
4. Draining stale events at startup covers a full burst, and stops at max_polls
5. Bug 4: an unplugged adapter (a port error) calls on_lost and stops the reader; the process is
   not killed. Other read failures are logged and survived
"""

import errno
import time

from pc_tool import event_pump, serial_link, wire_protocol
from pc_tool.wire_protocol import EventType, Flag
from test.common.asserts import assert_eq, logged_warnings
from test.common.fake_mcu import FakeSerialPort, crc16


def _packet(cmd_id=0, flags=0, seq=0, mem=0, address=0, length=0, data=0, crc_ok=True) -> bytes:
    body = (bytes([cmd_id, flags, seq, mem]) + address.to_bytes(4, "little") + length.to_bytes(2, "little")
            + data.to_bytes(4, "little"))
    crc = crc16(body) ^ (0 if crc_ok else 0xFFFF)
    return bytes([0xAA]) + body + crc.to_bytes(2, "little") + bytes([0x55])


def _watchpoint_event(slot=1, old=0x11, new=0x22) -> bytes:
    return _packet(flags=Flag.EVENT_PACKET | Flag.ACK_NACK, seq=slot, mem=EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT,
                   address=old, length=4, data=new)


def _pump(uart_idle=False, port=None, **callbacks):
    port = port or FakeSerialPort(answer=lambda request: b"")
    link = serial_link.SerialLink("fake")
    link.open(port)
    events = []
    pump = event_pump.EventPump(link, uart_idle, on_event=events.append, **callbacks)
    return pump, link, port, events


def _until(condition, timeout=2.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


# ---------------------------------------------------------------- 1.-2. routing

def test_packets_are_routed_by_kind():
    pump, link, port, events = _pump()
    pump.start()
    try:
        port.inject(_watchpoint_event())
        port.inject(_packet(flags=Flag.ACK_NACK))                       # an empty poll answer
        port.inject(_packet(cmd_id=0x05, flags=Flag.ACK_NACK))          # a reply to PING
        assert _until(lambda: events and not link.replies.empty())
    finally:
        pump.stop()
    assert_eq(events, [wire_protocol.Event(EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT, 1, 0x11, 4, 0x22)])
    assert_eq([p.cmd_id for p in list(link.replies.queue)], [0x05])


def test_a_corrupted_packet_is_dropped_and_reading_goes_on():
    pump, link, port, events = _pump()
    with logged_warnings("pc_tool.event_pump") as warnings:
        pump.start()
        try:
            port.inject(_packet(cmd_id=0x05, flags=Flag.ACK_NACK, crc_ok=False))
            port.inject(_watchpoint_event())
            assert _until(lambda: events)
        finally:
            pump.stop()
    assert_eq(link.replies.empty(), True)
    assert_eq(len(warnings), 1)
    assert warnings[0].startswith("Dropped a corrupted packet (CRC mismatch"), warnings


# ---------------------------------------------------------------- 3. polling

def test_uart_idle_mode_polls_and_polls_again_after_an_event():
    pending = [_watchpoint_event(slot=0), _watchpoint_event(slot=1)]

    def mcu(request):                                   # one pending event per poll, then empty answers
        return pending.pop(0) if pending else _packet(flags=Flag.ACK_NACK)

    port = FakeSerialPort(answer=mcu)
    pump, link, port, events = _pump(uart_idle=True, port=port)
    pump.start()
    try:
        assert _until(lambda: len(events) == 2, timeout=1.0)
    finally:
        pump.stop()
    assert_eq([e.slot for e in events], [0, 1])          # the burst drained without waiting a poll period


def test_poll_mode_sends_nothing():
    pump, link, port, events = _pump(uart_idle=False)
    pump.start()
    time.sleep(0.2)
    pump.stop()
    assert_eq(port.written, [])


# ---------------------------------------------------------------- 4. stale events

def _stale(count: int):
    pending = [_watchpoint_event() for _ in range(count)]
    return FakeSerialPort(answer=lambda request: pending.pop(0) if pending else _packet(flags=Flag.ACK_NACK)), pending


def test_drain_covers_a_full_burst():
    # One event per poll; the most the MCU can have pending is 4 breakpoints + 4 watchpoints + 2 error counters.
    port, pending = _stale(10)
    pump, *_ = _pump(uart_idle=True, port=port)
    assert_eq(pump.drain_stale_events(), 10)
    assert_eq(pending, [])


def test_drain_respects_max_polls():
    port, pending = _stale(10)
    pump, *_ = _pump(uart_idle=True, port=port)
    assert_eq(pump.drain_stale_events(max_polls=3), 3)
    assert_eq(len(pending), 7)


# ---------------------------------------------------------------- 5. bug 4

class _UnpluggedPort(FakeSerialPort):
    def read(self, size=1):
        raise OSError(errno.EIO, "Input/output error")


def test_an_unplugged_adapter_reports_lost_and_stops():
    lost = []
    pump, *_ = _pump(port=_UnpluggedPort(), on_lost=lambda: lost.append(True))
    pump.start()
    assert _until(lambda: lost)
    pump.stop()
    assert_eq((lost, pump.lost), ([True], True))
    assert_eq(any(t.is_alive() for t in pump._threads), False)


class _FlakyReader(FakeSerialPort):
    """A bug in a read (not a port error): the reader logs it and keeps reading."""

    def __init__(self):
        super().__init__(answer=lambda request: b"")
        self.failures = 2

    def read(self, size=1):
        if self.failures:
            self.failures -= 1
            raise ValueError("bad byte")
        return super().read(size)


def test_a_failing_read_that_is_not_a_port_error_is_survived():
    pump, link, port, events = _pump(port=_FlakyReader())
    pump.start()
    try:
        port.inject(_watchpoint_event())
        assert _until(lambda: events, timeout=3.0)
    finally:
        pump.stop()
    assert_eq(pump.lost, False)
