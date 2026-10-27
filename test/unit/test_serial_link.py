"""
SERIAL LINK TESTS (pc_tool/serial_link.py)

Coverage:
1. Opening: any pyserial URL (loop://), a device file that never appears is a LinkError
2. Framing: 18 bytes from a start byte; noise skipped; a packet split over reads; None on timeout
3. Bug 3: a reader waiting for bytes blocks on the port instead of spinning
4. Startup sync: an echo means connected; silence is a warning, not a hang
5. While a command holds the link, no other thread can send (the event poll is skipped)
"""

import threading
import time

from pc_tool import serial_link, wire_protocol
from pc_tool.serial_link import LinkError, SerialLink
from test.common.asserts import assert_eq, logged_warnings
from test.common.fake_mcu import FakeSerialPort

_PING = wire_protocol.encode(wire_protocol.Command(name="PING", id=wire_protocol.CommandId.PING))


def _link(port=None) -> tuple[SerialLink, FakeSerialPort]:
    port = port or FakeSerialPort(answer=lambda request: b"")
    link = SerialLink("fake")
    link.open(port)
    return link, port


# ---------------------------------------------------------------- 1. opening

def test_any_pyserial_url_opens():
    link = SerialLink("loop://", reset_delay=0)
    link.open()
    try:
        link.send(_PING)                              # loop:// echoes what is written
        assert_eq(link.read_packet(timeout=1.0), _PING)
    finally:
        link.close()
    assert_eq(link.is_open, False)


def test_a_device_that_never_appears_is_a_link_error():
    saved, serial_link._PORT_APPEAR_WAIT = serial_link._PORT_APPEAR_WAIT, 0.2
    try:
        SerialLink("/dev/does-not-exist-mdt", reset_delay=0).open()
    except LinkError as exc:
        assert "did not appear" in str(exc), exc
    else:
        raise AssertionError("no LinkError")
    finally:
        serial_link._PORT_APPEAR_WAIT = saved


# ---------------------------------------------------------------- 2. framing

def test_noise_before_the_start_byte_is_skipped():
    link, port = _link()
    port.inject(b"\x00\x13\x37" + _PING + b"\x55")
    assert_eq(link.read_packet(timeout=0.5), _PING)
    assert_eq(link.read_packet(timeout=0.1), None)    # the stray 0x55 is not a packet


def test_a_packet_split_over_reads_is_joined():
    link, port = _link()
    threading.Timer(0.1, port.inject, args=(_PING[7:],)).start()
    port.inject(_PING[:7])
    assert_eq(link.read_packet(timeout=1.0), _PING)


def test_nothing_on_the_wire_times_out():
    link, _ = _link()
    started = time.monotonic()
    assert_eq(link.read_packet(timeout=0.2), None)
    assert 0.15 < time.monotonic() - started < 0.5


# ---------------------------------------------------------------- 3. bug 3: no busy wait

def test_waiting_for_bytes_uses_no_cpu():
    link, _ = _link()
    cpu = time.process_time()
    link.read_packet(timeout=0.5)
    assert time.process_time() - cpu < 0.1, "read_packet spins while the line is idle"


# ---------------------------------------------------------------- 4. startup sync

def test_sync_echo_means_connected():
    link, port = _link(FakeSerialPort())
    assert_eq(link.sync(_PING), True)
    assert_eq(port.written, [_PING])


def test_sync_silence_warns_and_returns():
    saved, serial_link._SYNC_WAIT = serial_link._SYNC_WAIT, 0.2
    try:
        link, _ = _link()
        with logged_warnings("pc_tool.serial_link") as warnings:
            assert_eq(link.sync(_PING), False)
    finally:
        serial_link._SYNC_WAIT = saved
    assert_eq(warnings, ["Startup ping echo mismatch: expected 18, got 0."])


# ---------------------------------------------------------------- 5. the lock

def test_no_other_thread_sends_while_a_command_holds_the_link():
    link, port = _link()
    results = []
    with link.lock:                                   # what the command client does for one exchange
        worker = threading.Thread(target=lambda: results.append(link.try_send(b"poll")))
        worker.start()
        worker.join()
    assert_eq(results, [False])
    assert_eq(link.try_send(_PING), True)             # free again once the command is done
    assert_eq(port.written, [_PING])
