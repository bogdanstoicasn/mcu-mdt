"""The background side of the link: one thread reads every packet, one polls for events.

The reader decodes each packet (size, fences, CRC) and routes it: an event goes to on_event,
an empty poll answer is dropped, and anything else is a reply for the command client. A packet
that fails to decode is dropped with a warning; the command waiting for it times out and retries.

In UART-idle mode (STM32) the MCU only reports an event when polled, so a poller sends a
CMD_ID 0 packet every EVENT_POLL_INTERVAL, and the reader polls again right after each event to
drain a burst. In poll mode (AVR) the firmware sends events on its own.

The pump never prints: events and a lost link are reported through the callbacks.
"""

import logging
import threading
from collections.abc import Callable

from pc_tool import serial_link, wire_protocol

log = logging.getLogger(__name__)

EVENT_POLL_INTERVAL = 0.5       # seconds
_READ_TIMEOUT = 0.2             # seconds; how fast the reader notices stop()
_MAX_READ_ERRORS = 10           # consecutive read errors before the reader gives up
_POLL_PACKET = wire_protocol.encode(wire_protocol.Command(name="POLL", id=0x00))


class EventPump:
    def __init__(self, link: serial_link.SerialLink, uart_idle: bool,
                 on_event: Callable[[wire_protocol.Event], None],
                 on_lost: Callable[[], None] = lambda: None) -> None:
        self._link = link
        self._uart_idle = uart_idle
        self._on_event = on_event
        self._on_lost = on_lost         # the link died (unplugged): the app should shut down
        self.lost = False
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def drain_stale_events(self, max_polls: int = 16, per_poll_timeout: float = 0.2) -> int:
        """Drop events left over from an earlier session. Call before start(), so the drain has
        the link to itself. Returns how many were dropped."""
        dropped = 0
        for _ in range(max_polls):
            if self._uart_idle:
                self._link.send(_POLL_PACKET)
            raw = self._link.read_packet(timeout=per_poll_timeout)
            if raw is None or not _is_event_packet(raw):
                break                   # quiet, or a poll answer / stray reply: nothing left pending
            log.info("Dropped stale event at startup: %s", raw.hex())
            dropped += 1
        if dropped:
            log.info("Drained %d stale event(s) at startup.", dropped)
        return dropped

    def start(self) -> None:
        workers = [self._read_forever] + ([self._poll_forever] if self._uart_idle else [])
        self._threads = [threading.Thread(target=w, name=w.__name__, daemon=True) for w in workers]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=2.0)

    # ---------------------------------------------------------------- threads

    def _read_forever(self) -> None:
        errors = 0
        while not self._stop.is_set():
            try:
                raw = self._link.read_packet(timeout=_READ_TIMEOUT)
                errors = 0
            except Exception as exc:    # the reader must outlive a bad read; a port error ends the link
                if self._stop.is_set():
                    return
                errors += 1
                if isinstance(exc, OSError) or errors >= _MAX_READ_ERRORS:   # SerialException is an OSError
                    log.error("Board disconnected (%s). Exiting.", exc, extra={"code": "(5)"})
                    self.lost = True
                    self._stop.set()
                    self._on_lost()
                    return
                log.error("Serial read failed: %s", exc, extra={"code": "(5)"})
                self._stop.wait(0.5)
                continue
            if raw is not None:
                self._route(raw)

    def _route(self, raw: bytes) -> None:
        try:
            packet = wire_protocol.decode(raw)
        except wire_protocol.PacketError as exc:
            log.warning("Dropped a corrupted packet (%s): %s", exc, raw.hex())
            return
        if packet.cmd_id == 0 and packet.is_event:
            self._deliver(packet)
            if self._uart_idle:
                self._link.try_send(_POLL_PACKET)     # more may be pending
        elif not packet.is_poll_ack:
            self._link.replies.put(packet)

    def _deliver(self, packet: wire_protocol.Packet) -> None:
        try:
            self._on_event(wire_protocol.decode_event(packet))
        except Exception as exc:        # a bad event or a failing callback must not stop the reader
            log.error("Event dropped: %s", exc, extra={"code": "(5)"})

    def _poll_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self._link.send(_POLL_PACKET)
            except Exception as exc:    # a failed poll is retried on the next tick
                if not self._stop.is_set():
                    log.error("Event poll failed: %s", exc, extra={"code": "(5)"})
            self._stop.wait(EVENT_POLL_INTERVAL)


def _is_event_packet(raw: bytes) -> bool:
    return raw[wire_protocol.Offset.CMD_ID] == 0 and bool(raw[wire_protocol.Offset.FLAGS] & wire_protocol.Flag.EVENT_PACKET)
