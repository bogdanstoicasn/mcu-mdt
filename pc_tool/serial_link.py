"""The serial port to the MCU: open and sync, framed reads, locked writes, and the reply queue.

Any port pyserial can open works: a device (/dev/ttyUSB0, COM3), socket://host:port (Renode,
the fake MCU), rfc2217://, loop://. Tests can hand open() an already-open serial-like object.

Reads block on the port with a short timeout, so a reader waiting for bytes uses no CPU.
"""

import logging
import os
import queue
import threading
import time

import serial

from pc_tool import MdtError, wire_protocol

log = logging.getLogger(__name__)

_READ_SLICE = 0.05          # seconds one port read may block; bounds how fast a reader sees a stop
_PORT_APPEAR_WAIT = 5.0     # seconds to wait for a device file to appear (simavr creates its pty late)
_SYNC_WAIT = 5.0            # seconds to wait for the startup ping's echo


class LinkError(MdtError):
    """The port can't be opened, or was lost."""


class SerialLink:
    """One open port. Every write takes `lock`; a command holds it for its whole exchange, so the
    event poll can't slip a packet in between. Replies to commands wait in `replies`."""

    def __init__(self, port: str, baudrate: int = 19200, reset_delay: float = 2.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.reset_delay = reset_delay      # boards that reset on open (Arduino) need it
        self.lock = threading.RLock()
        self.replies: queue.Queue[wire_protocol.Packet] = queue.Queue()
        self._serial = None
        self._rx = bytearray()

    # ---------------------------------------------------------------- lifecycle

    def open(self, port_object=None) -> None:
        """Open the port, or adopt *port_object*, an open serial-like object (tests)."""
        if port_object is not None:
            self._serial = port_object
            return
        try:
            _wait_for_device(self.port)
            self._serial = serial.serial_for_url(self.port, baudrate=self.baudrate, timeout=_READ_SLICE)
        except (serial.SerialException, ValueError) as exc:
            raise LinkError(str(exc)) from exc
        if self.reset_delay > 0:
            time.sleep(self.reset_delay)

    def sync(self, ping: bytes) -> bool:
        """Send the startup ping and wait for its echo: True when the MCU answered."""
        self.drop_input()
        self.send(ping)
        echoed = bytearray()
        deadline = time.monotonic() + _SYNC_WAIT
        while len(echoed) < wire_protocol.PACKET_SIZE and time.monotonic() < deadline:
            echoed += self._serial.read(wire_protocol.PACKET_SIZE - len(echoed))
        if len(echoed) < wire_protocol.PACKET_SIZE:
            log.warning("Startup ping echo mismatch: expected %d, got %d.", wire_protocol.PACKET_SIZE, len(echoed))
            return False
        log.info("Startup ping successful — MCU is connected.")
        return True

    def close(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except Exception:       # the port may already be gone (unplugged); closing is all that's left
            pass
        self._serial.close()
        self._serial = None

    def drop_input(self) -> None:
        """Forget every byte received and not read yet."""
        self._serial.reset_input_buffer()
        self._rx.clear()

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # ---------------------------------------------------------------- I/O

    def send(self, packet: bytes) -> None:
        with self.lock:
            if not self.is_open:
                raise LinkError("Serial port is not open.")
            self._serial.write(packet)
            self._serial.flush()

    def try_send(self, packet: bytes) -> bool:
        """Send unless another thread holds the link (a command in flight); never blocks."""
        if not self.lock.acquire(blocking=False):
            return False
        try:
            self.send(packet)
            return True
        finally:
            self.lock.release()

    def read_packet(self, timeout: float) -> bytes | None:
        """The next 18 bytes that start with the start byte, or None after *timeout* seconds.
        Bytes before a start byte are skipped (resync after noise or a partial packet)."""
        deadline = time.monotonic() + timeout
        while True:
            start = self._rx.find(wire_protocol.START_BYTE)
            if start < 0:
                self._rx.clear()
            elif start > 0:
                del self._rx[:start]
            if len(self._rx) >= wire_protocol.PACKET_SIZE:
                packet = bytes(self._rx[:wire_protocol.PACKET_SIZE])
                del self._rx[:wire_protocol.PACKET_SIZE]
                return packet
            if time.monotonic() >= deadline or not self.is_open:
                return None
            self._rx += self._serial.read(max(1, self._serial.in_waiting))   # blocks up to _READ_SLICE

    # ---------------------------------------------------------------- replies

    def next_reply(self, timeout: float) -> wire_protocol.Packet | None:
        try:
            return self.replies.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None

    def drop_replies(self) -> None:
        """Forget replies nobody waited for (a command that timed out, a stray NACK)."""
        while True:
            try:
                self.replies.get_nowait()
            except queue.Empty:
                return


def _wait_for_device(port: str) -> None:
    """A device file (/dev/..., /tmp/simavr-uart0) may appear a moment after the board or simulator starts."""
    if not port.startswith("/"):
        return
    deadline = time.monotonic() + _PORT_APPEAR_WAIT
    while not os.path.exists(port):
        if time.monotonic() >= deadline:
            raise LinkError(f"Port '{port}' did not appear within {_PORT_APPEAR_WAIT:.0f}s. "
                            f"Check the board is connected and the port is correct "
                            f"(e.g. /dev/ttyUSB0 or /dev/ttyACM0)")
        time.sleep(0.1)
