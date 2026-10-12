"""
HOST-SIDE EVENT FORMATTING TESTS FOR MCU-MDT

Covers how the PC shows events from the state-based MCU event system:
1. Breakpoint hit shows the total hit count
2. Buffer overflow / failed packet show how many occurred
3. Draining stale events at startup covers a full burst
"""

from pc_tool.common.enums import MDT_PACKET_SIZE, EventType, MDTFlags, MDTOffset
from pc_tool.event import EventHandler
from test.common.asserts import assert_eq


def test_breakpoint_hit_shows_hit_count():
    msg = EventHandler._format_event(EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT, 2, 0, 0, 5)
    assert "slot=2" in msg and "hit_count=5" in msg


def test_failed_packet_shows_count():
    msg = EventHandler._format_event(EventType.INTERNAL_MDT_EVENT_FAILED_PACKET, 0, 0, 0, 3)
    assert_eq(msg, "[Event] INTERNAL_MDT_EVENT_FAILED_PACKET (count=3)")


def test_buffer_overflow_shows_count():
    msg = EventHandler._format_event(EventType.INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, 0, 0, 0, 255)
    assert_eq(msg, "[Event] INTERNAL_MDT_EVENT_BUFFER_OVERFLOW (count=255)")


class _FakeLink:
    """Minimal link: hands out `count` stale event packets, then silence."""

    def __init__(self, count: int):
        self.remaining = count

    def send_packet(self, pkt):
        pass

    def read_packet(self, timeout=None):
        if self.remaining == 0:
            return None
        self.remaining -= 1
        pkt = bytearray(MDT_PACKET_SIZE)
        pkt[MDTOffset.FLAGS] = MDTFlags.EVENT_PACKET
        return bytes(pkt)


def test_drain_default_covers_a_full_burst():
    # The MCU reports one event per poll. The most it can have pending is
    # 4 breakpoints + 4 watchpoints + 2 error counters = 10.
    link = _FakeLink(10)
    assert_eq(EventHandler(link, uart_idle=True).drain_stale_events(), 10)
    assert_eq(link.remaining, 0)


def test_drain_respects_max_polls():
    link = _FakeLink(10)
    assert_eq(EventHandler(link, uart_idle=True).drain_stale_events(max_polls=3), 3)
    assert_eq(link.remaining, 7)
