import os
import queue
import time
import serial

from pc_tool.common.enums import MDT_PACKET_SIZE, FenceType
from pc_tool.common.logger import MDTLogger

_START_BYTE = FenceType.START_BYTE.to_bytes(1, "little")


class MCUSerialLink:
    def __init__(
        self,
        port: str,
        baudrate: int = 19200,
        timeout: float = 1.0,
        reset_delay: float = 2.0,
        startup_ping: bytes | None = None,
    ) -> None:
        self.port          = port
        self.baudrate      = baudrate
        self.timeout       = timeout
        self.reset_delay   = reset_delay
        self.startup_ping  = startup_ping
        self.running       = True
        self.response_queue = queue.Queue()
        self.event_queue    = queue.Queue()
        self._rx_buf       = bytearray()
        self.ser           = None

    # Lifecycle
    def open(self) -> None:
        if self.ser is not None and self.ser.is_open:
            return

        port = self._resolve_port(self.port)

        serial_kwargs = dict(
            baudrate=self.baudrate,
            timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

        self.ser = (
            serial.serial_for_url(port, **serial_kwargs)
            if port.startswith("socket://")
            else serial.Serial(port, **serial_kwargs)
        )

        if self.reset_delay > 0:
            time.sleep(self.reset_delay)

        if self.startup_ping:
            self._synch_with_mcu()

    def close(self) -> None:
        self.running = False
        if self.ser:
            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception:
                pass
            self.ser.close()
            self.ser = None

    @staticmethod
    def _resolve_port(port: str, wait: float = 5.0) -> str:
        """Resolve the port path, polling up to ``wait`` seconds if it doesn't exist yet.

        Useful when simavr creates ``/tmp/simavr-uart0`` asynchronously after startup.
        Raises ``SerialException`` on timeout. KeyboardInterrupt is never caught.
        """
        if os.path.exists(port):
            return port

        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(0.1)
            if os.path.exists(port):
                return port

        raise serial.SerialException(
            f"Port '{port}' did not appear within {wait:.0f}s. Is simavr running?"
        )

    def _synch_with_mcu(self) -> None:
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(self.startup_ping)
        self.ser.flush()

        echoed   = bytearray()
        deadline = time.monotonic() + 5.0

        while len(echoed) < MDT_PACKET_SIZE and time.monotonic() < deadline:
            if self.ser.in_waiting:
                echoed += self.ser.read(self.ser.in_waiting)

        if len(echoed) < MDT_PACKET_SIZE:
            MDTLogger.warning(
                f"Startup ping echo mismatch: expected {MDT_PACKET_SIZE}, got {len(echoed)}."
            )
            return

        MDTLogger.info("Startup ping successful — MCU is connected.")

    # I/O
    def send_packet(self, packet: bytes) -> None:
        if self.ser is None or not self.ser.is_open:
            raise RuntimeError("Serial port is not open.")
        self.ser.write(packet)
        self.ser.flush()

    def read_packet(self, timeout: float = 1.0) -> bytes | None:
        """Read one full MDT packet from UART, resyncing on the start byte if needed."""
        if self.ser is None or not self.ser.is_open:
            return None

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.ser.in_waiting:
                self._rx_buf += self.ser.read(self.ser.in_waiting)

            idx = self._rx_buf.find(_START_BYTE)
            if idx == -1:
                self._rx_buf.clear()
                continue

            if idx > 0:
                self._rx_buf = self._rx_buf[idx:]

            if len(self._rx_buf) >= MDT_PACKET_SIZE:
                pkt          = bytes(self._rx_buf[:MDT_PACKET_SIZE])
                self._rx_buf = self._rx_buf[MDT_PACKET_SIZE:]
                return pkt

        return None

    # Queue management
    def get_response_packet(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self.response_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_event_packet(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self.event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def push_back_packet(self, pkt: bytes) -> None:
        self.response_queue.put(pkt)

    def push_back_event_packet(self, pkt: bytes) -> None:
        self.event_queue.put(pkt)
