import os
import sys
import time
import threading

from pc_tool.common.enums import MDTFlags, MDTOffset, EventType
from pc_tool.common.protocol import serialize_command_packet
from pc_tool.common.dataclasses import Command
from pc_tool.common.logger import MDTLogger

EVENT_POLL_INTERVAL = 0.5  # seconds

_POLL_COMMAND = Command(name="POLL", id=0x00, mem=None, address=0, data=None)
_POLL_PACKET  = serialize_command_packet(_POLL_COMMAND, seq=0, multi=False, last=False)


class EventHandler:
    """Manages the background threads that read packets from UART and dispatch events.

    Usage::

        handler = EventHandler(serial_link, uart_idle=True)
        threads = handler.start()
        ...
        # threads are daemon threads; they die with the process
    """

    def __init__(self, serial_link, uart_idle: bool = False) -> None:
        self._link      = serial_link
        self._uart_idle = uart_idle

    # Packet parsing
    @staticmethod
    def _is_event(pkt: bytes) -> bool:
        return (
            pkt[MDTOffset.CMD_ID] == 0
            and bool(pkt[MDTOffset.FLAGS] & MDTFlags.EVENT_PACKET)
        )

    @staticmethod
    def _is_clean_poll_ack(pkt: bytes) -> bool:
        flags = pkt[MDTOffset.FLAGS]
        return (
            pkt[MDTOffset.CMD_ID] == 0
            and bool(flags & MDTFlags.ACK_NACK)
            and not bool(flags & MDTFlags.STATUS_ERROR)
        )

    # Formatting event packets
    @staticmethod
    def _parse_event_fields(pkt: bytes) -> tuple[int, int, int, int, int]:
        """Return (event_type, slot_id, address, length, data)."""
        event_type = pkt[MDTOffset.MEM_ID]
        slot_id    = pkt[MDTOffset.SEQ]
        address    = int.from_bytes(pkt[MDTOffset.ADDRESS : MDTOffset.ADDRESS + 4], "little")
        length     = int.from_bytes(pkt[MDTOffset.LENGTH  : MDTOffset.LENGTH  + 2], "little")
        data       = int.from_bytes(pkt[MDTOffset.DATA    : MDTOffset.DATA    + 4], "little")
        return event_type, slot_id, address, length, data

    @staticmethod
    def _format_event(ev: EventType, slot_id: int, address: int, length: int, data: int) -> str:
        if ev == EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT:
            return f"[Event] {ev.name} (slot={slot_id}, hit_count={data})"
        if ev == EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT:
            return (
                f"[Event] {ev.name} "
                f"(slot={slot_id}, old=0x{address:08X}, new=0x{data:08X}, width={length})"
            )
        # Generic fallback: BUFFER_OVERFLOW, FAILED_PACKET, future types
        return (
            f"[Event] {ev.name} "
            f"(slot={slot_id}, address=0x{address:08X}, length={length}, data=0x{data:08X})"
        )


    def rx_worker(self) -> None:
        """Read packets from UART and route them to the appropriate queue.

        Event packets go to the event queue; everything else (NACKs, normal
        command responses) goes to the response queue for the caller waiting
        on ``get_response_packet()``.  Clean poll ACKs are discarded silently.
        """
        while self._link.running:
            try:
                pkt = self._link.read_packet(timeout=1.0)
                if pkt is None:
                    continue

                if self._is_event(pkt):
                    self._link.push_back_event_packet(pkt)
                elif self._is_clean_poll_ack(pkt):
                    pass  # discard
                else:
                    self._link.push_back_packet(pkt)

            except OSError as exc:
                if exc.errno == 5:  # EIO — USB-serial adapter disconnected
                    MDTLogger.error("\nBoard disconnected. Exiting.")
                    self._link.running = False
                    os._exit(1)
                if self._link.running:
                    MDTLogger.error(f"\n[RX Worker] {exc}\n> ", code=5)
            except Exception as exc:
                if self._link.running:
                    MDTLogger.error(f"\n[RX Worker] {exc}\n> ", code=5)

    def _event_listener(self) -> None:
        """Consume event packets from the event queue and print them asynchronously."""
        while self._link.running:
            try:
                pkt = self._link.get_event_packet(timeout=1.0)
                if pkt is None:
                    continue

                event_type, slot_id, address, length, data = self._parse_event_fields(pkt)
                ev  = EventType(event_type)
                msg = self._format_event(ev, slot_id, address, length, data)

                sys.stdout.write(f"\r\033[K{msg}\n> ")
                sys.stdout.flush()

            except Exception as exc:
                if self._link.running:
                    MDTLogger.error(f"\n[Event Listener] {exc}\n> ", code=5)

    def _event_poll_worker(self) -> None:
        """Send a CMD_ID=0 poll packet every ``EVENT_POLL_INTERVAL`` seconds.

        The MCU fills the response with any pending event data and sets
        FLAG_EVENT if one is present.  ``rx_worker`` routes that response to
        the event queue.  Sending is fire-and-forget; no response is consumed
        here.
        """
        while self._link.running:
            try:
                self._link.send_packet(_POLL_PACKET)
            except Exception as exc:
                if self._link.running:
                    MDTLogger.error(f"\n[Poll Worker] {exc}\n> ", code=5)

            time.sleep(EVENT_POLL_INTERVAL)


    def start(self) -> list[threading.Thread]:
        """Start all background threads and return them.

        Threads are daemon threads — they die with the process automatically.
        In UART idle mode an extra poll thread is added so the MCU can drain
        its event queue.  In poll mode the MCU handles that via
        ``mcu_mdt_poll()`` and no extra thread is needed.
        """
        rx_thread = threading.Thread(target=self.rx_worker,       daemon=True)
        ev_thread = threading.Thread(target=self._event_listener, daemon=True)

        rx_thread.start()
        ev_thread.start()

        threads = [rx_thread, ev_thread]

        if self._uart_idle:
            poll_thread = threading.Thread(target=self._event_poll_worker, daemon=True)
            poll_thread.start()
            threads.append(poll_thread)
            MDTLogger.info("UART idle interrupt mode — event poll thread started.")
        else:
            MDTLogger.info("Poll mode — MCU drains events via mcu_mdt_poll(), no event poll thread needed.")

        return threads


def start_async_handlers(serial_link, uart_idle: bool = False) -> list[threading.Thread]:
    return EventHandler(serial_link, uart_idle=uart_idle).start()


def rx_worker(serial_link) -> None:
    """Module-level shim so test_hardware.py can pass this as a thread target."""
    EventHandler(serial_link).rx_worker()