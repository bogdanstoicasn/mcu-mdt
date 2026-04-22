import sys
import time
import threading
from pc_tool.common.enums import MDTFlags, MDTOffset, EventType
from pc_tool.common.protocol import serialize_command_packet
from pc_tool.common.dataclasses import Command
from pc_tool.common.logger import MDTLogger

EVENT_POLL_INTERVAL = 0.5  # seconds


def rx_worker(serial_link):
    """
    Continuously reads packets from UART and dispatches them
    to the appropriate queues.
    """

    while serial_link.running:
        try:
            pkt = serial_link.read_packet(timeout=1.0)

            if pkt is None:
                continue

            flags  = pkt[MDTOffset.FLAGS]
            cmd_id = pkt[MDTOffset.CMD_ID]

            if cmd_id == 0 and (flags & MDTFlags.EVENT_PACKET):
                serial_link.push_back_event_packet(pkt)
            elif cmd_id == 0 and not (flags & MDTFlags.EVENT_PACKET):
                pass  # plain poll ACK — no event pending, discard silently
            else:
                serial_link.push_back_packet(pkt)

        except Exception as e:
            if serial_link.running:
                MDTLogger.error(f"\n[RX Worker Error] {e}\n> ", code=5)


def event_listener(serial_link):
    """
    Consumes event packets and prints them asynchronously.
    """

    while serial_link.running:
        try:
            pkt = serial_link.get_event_packet(timeout=1.0)

            if pkt is None:
                continue

            event_type = pkt[MDTOffset.MEM_ID]   # mem_id encodes the event type
            slot_id    = pkt[MDTOffset.SEQ]       # seq encodes the BP/WP slot ID

            address = int.from_bytes(
                pkt[MDTOffset.ADDRESS:MDTOffset.ADDRESS + 4],
                byteorder='little'
            )
            length = int.from_bytes(
                pkt[MDTOffset.LENGTH:MDTOffset.LENGTH + 2],
                byteorder='little'
            )
            data = int.from_bytes(
                pkt[MDTOffset.DATA:MDTOffset.DATA + 4],
                byteorder='little'
            )

            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

            ev = EventType(event_type)

            if ev == EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT:
                MDTLogger.info(
                    f"[Event] {ev.name} "
                    f"(slot={slot_id}, hit_count={data})"
                )
            elif ev == EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT:
                MDTLogger.info(
                    f"[Event] {ev.name} "
                    f"(slot={slot_id}, old=0x{address:08X}, new=0x{data:08X}, width={length})"
                )
            else:
                # Generic fallback for BUFFER_OVERFLOW, FAILED_PACKET, future types
                MDTLogger.info(
                    f"[Event] {ev.name} "
                    f"(slot={slot_id}, address=0x{address:08X}, length={length}, data=0x{data:08X})"
                )

            sys.stdout.write("> ")
            sys.stdout.flush()

        except Exception as e:
            if serial_link.running:
                MDTLogger.error(f"\n[Event Listener Error] {e}\n> ", code=5)


def event_poll_worker(serial_link):
    """
    Sends a CMD_ID=0 poll packet every EVENT_POLL_INTERVAL seconds.
    The MCU fills the response with any pending event data and sets FLAG_EVENT
    if one is present. rx_worker routes that response to the event queue.
    No response is consumed here — sending is fire-and-forget.
    """
    poll_command = Command(
        name="POLL",
        id=0x00,
        mem=None,
        address=0,
        data=None
    )
    poll_packet = serialize_command_packet(poll_command, seq=0, multi=False, last=False)

    while serial_link.running:
        try:
            serial_link.send_packet(poll_packet)
        except Exception as e:
            if serial_link.running:
                MDTLogger.error(f"\n[Poll Worker Error] {e}\n> ", code=5)

        time.sleep(EVENT_POLL_INTERVAL)


def start_async_handlers(serial_link, uart_idle: bool = False):
    """
    Starts RX worker and event listener threads.
    """

    rx_thread = threading.Thread(
        target=rx_worker,
        args=(serial_link,),
        daemon=True
    )

    event_thread = threading.Thread(
        target=event_listener,
        args=(serial_link,),
        daemon=True
    )

    rx_thread.start()
    event_thread.start()

    threads = [rx_thread, event_thread]

    if uart_idle:
        poll_thread = threading.Thread(
            target=event_poll_worker,
            args=(serial_link,),
            daemon=True
        )
        poll_thread.start()
        threads.append(poll_thread)
        MDTLogger.info("UART idle interrupt mode — event poll thread started.")
    else:
        MDTLogger.info("Poll mode — MCU drains events via mcu_mdt_poll(), no event poll thread needed.")

    return threads