"""
HOST-SIDE EVENT FORMATTING TESTS FOR MCU-MDT

Covers how the PC shows events from the state-based MCU event system:
1. Breakpoint hit shows the total hit count
2. Buffer overflow / failed packet show how many occurred
"""

from test.common.asserts import assert_eq
from pc_tool.event import EventHandler
from pc_tool.common.enums import EventType


def test_breakpoint_hit_shows_hit_count():
    msg = EventHandler._format_event(EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT, 2, 0, 0, 5)
    assert "slot=2" in msg and "hit_count=5" in msg


def test_failed_packet_shows_count():
    msg = EventHandler._format_event(EventType.INTERNAL_MDT_EVENT_FAILED_PACKET, 0, 0, 0, 3)
    assert_eq(msg, "[Event] INTERNAL_MDT_EVENT_FAILED_PACKET (count=3)")


def test_buffer_overflow_shows_count():
    msg = EventHandler._format_event(EventType.INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, 0, 0, 0, 255)
    assert_eq(msg, "[Event] INTERNAL_MDT_EVENT_BUFFER_OVERFLOW (count=255)")
