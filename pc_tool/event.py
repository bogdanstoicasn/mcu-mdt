import sys
import threading
from pc_tool.common.enums import MDTFlags, MDTOffset, EventType
from pc_tool.common.logger import MDTLogger


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

            flags = pkt[MDTOffset.FLAGS]

            if flags & MDTFlags.EVENT_PACKET and pkt[MDTOffset.CMD_ID] == 0:
                serial_link.push_back_event_packet(pkt)
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

            event_type = pkt[MDTOffset.DATA + 3]
            event_data = int.from_bytes(pkt[MDTOffset.DATA:MDTOffset.DATA + 3], byteorder='little')

            # Clear the current line (erases dangling "> " prompt), print event, reprint prompt
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            MDTLogger.info(f"[Event] {EventType(event_type).name} (data=0x{event_data:06X})")
            sys.stdout.write("> ")
            sys.stdout.flush()

        except Exception as e:
            if serial_link.running:
                MDTLogger.error(f"\n[Event Listener Error] {e}\n> ", code=5)


def start_async_handlers(serial_link):
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

    return rx_thread, event_thread