import shutil
import time

from pc_tool.common.logger import MDTLogger
from pc_tool.common.terminal import Terminal
from pc_tool.common.uart_io import MCUSerialLink
from pc_tool.parser import parse_packet
from pc_tool.wire_protocol import (
    WORD_SIZE,
    Command,
    Flag,
    Offset,
    PacketError,
    decode,
    encode,
    is_nack,
)

_REPLY_TIMEOUT = 1.0  # seconds per attempt
MAX_ATTEMPTS = 3      # sends per packet before giving up


def _is_reply_to(reply: bytes, request: bytes) -> bool:
    """An ACK echoes the request's command id, sequence and address. A NACK carries none of
    them, but it can only be ours: nothing else is sent while a command holds the link."""
    if is_nack(reply):
        return True
    echoed = (Offset.CMD_ID, Offset.SEQ, *range(Offset.ADDRESS, Offset.ADDRESS + 4))
    return bool(reply[Offset.FLAGS] & Flag.ACK_NACK) and all(reply[i] == request[i] for i in echoed)


class Commander:
    """Sends commands to the MCU and handles ACK/NACK/retry logic.

    Usage::

        commander = Commander(serial_link)
        commander.ping(ping_cmd)
        commander.execute(write_cmd)
    """

    def __init__(self, serial_link: MCUSerialLink) -> None:
        self._link = serial_link

    def _await_reply(self, request: bytes) -> bytes | None:
        """Wait for the reply to *request*; replies to anything else are dropped."""
        deadline = time.monotonic() + _REPLY_TIMEOUT
        while (left := deadline - time.monotonic()) > 0:
            reply = self._link.get_response_packet(timeout=left)
            if reply is None:
                return None
            if _is_reply_to(reply, request):
                return reply
            MDTLogger.info(f"Dropped a reply to another request: {reply.hex()}")
        return None

    def _send_with_retry(self, packet: bytes, seq: int) -> bytes | None:
        """Send a packet and retry up to MDT_MAX_RETRIES times.

        The link is held for the whole exchange, so the event poller cannot slip a packet in
        between; replies left over from an earlier timed-out command are dropped first.
        Returns the ACK packet on success, or None if all attempts fail.
        """
        with self._link.lock:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                self._link.drop_responses()
                self._link.send_packet(packet)
                ack = self._await_reply(packet)

                if ack is None:
                    MDTLogger.warning(
                        f"No response from MCU for seq={seq} "
                        f"(attempt {attempt}/{MAX_ATTEMPTS})."
                    )
                    continue

                if is_nack(ack):
                    MDTLogger.warning(
                        f"NACK received for seq={ack[Offset.SEQ]} "
                        f"(attempt {attempt}/{MAX_ATTEMPTS}), retrying..."
                    )
                    continue

                return ack

            return None

    @staticmethod
    def _log_ack(ack: bytes) -> None:
        """Log the received ACK packet and validate it."""
        MDTLogger.info(f"Received ACK: {ack.hex()}")
        parse_packet(ack)
        try:
            reply = decode(ack)
        except PacketError as exc:
            MDTLogger.error(str(exc), code=3)
            return
        if reply.is_error:
            MDTLogger.error("Command execution error indicated by status flag.", code=3)
            return
        MDTLogger.info("Command packet validation successful.")

    def ping(self, command: Command) -> None:
        """Send a ping command to the MCU."""
        packet = encode(command, seq=0, multi=False, last=False)
        MDTLogger.info(f"Serialized Ping Command Packet: {packet.hex()}")

        ack = self._send_with_retry(packet, seq=0)
        if ack is None:
            MDTLogger.error(f"Ping failed after {MAX_ATTEMPTS} attempts.", code=4)
            return

        self._log_ack(ack)

    def execute(self, command: Command) -> bool:
        """Send a command, splitting into word-sized chunks if needed. True when every chunk was ACKed."""
        is_write = command.data is not None
        length   = command.length if command.length is not None else WORD_SIZE
        seq      = 0

        for offset in range(0, length, WORD_SIZE):
            chunk_length = min(WORD_SIZE, length - offset)

            if is_write:
                chunk = command.data[offset : offset + chunk_length]
                if len(chunk) != WORD_SIZE:
                    chunk = chunk.ljust(WORD_SIZE, b'\x00')
            else:
                chunk = None

            chunk_cmd = Command(
                name    = command.name,
                id      = command.id,
                mem     = command.mem,
                address = command.address + offset,
                length  = chunk_length,
                data    = chunk,
            )

            packet = encode(
                chunk_cmd,
                seq   = seq,
                multi = length > WORD_SIZE,
                last  = offset + WORD_SIZE >= length,
            )

            MDTLogger.info(f"Serialized Command Packet: {packet.hex()}")

            ack = self._send_with_retry(packet, seq=seq)
            if ack is None:
                MDTLogger.error(
                    f"Command failed after {MAX_ATTEMPTS} attempts "
                    f"(seq={seq}). Aborting.",
                    code=4,
                )
                return False

            self._log_ack(ack)
            seq = (seq + 1) % 0xFF
        return True


# UI helpers + CLI commands — stateless, no class needed
def intro_text() -> str:
    """Generate centered intro text based on terminal width."""
    width = shutil.get_terminal_size().columns
    lines = [
        "MCU-MDT - Microcontroller Memory Debug Tool",
        "---------------------------------------",
        "Type 'HELP' to see available commands.",
    ]
    return "\n" + "\n".join(line.center(width) for line in lines) + "\n"


def help_command(command_data: dict = None) -> None:
    """Display available commands and their descriptions, formatted based on terminal width."""
    width = shutil.get_terminal_size().columns
    col1  = 32

    type_hints = {
        "uint32":        "<addr>",
        "uint32_or_str": "<addr|reg>",
        "uint16":        "<value>",
        "uint8":         "<value>",
        "str":           "<control>",
        "bytes":         "<hex>",
    }

    lines = ["─" * min(width, 72), "  MCU-MDT — Available Commands", "─" * min(width, 72)]

    if command_data:
        for name, info in command_data.get("commands", {}).items():
            params      = info.get("params", [])
            description = info.get("description", "")
            param_str   = " ".join(
                p.get("hint") or type_hints.get(p["type"], f"<{p['name']}>")
                for p in params
            )
            usage = f"  {name}" + (f" {param_str}" if param_str else "")

            if len(usage) < col1:
                lines.append(f"{usage.ljust(col1)}{description}")
            else:
                lines.append(usage)
                lines.append(f"{''.ljust(col1)}{description}")
    else:
        lines.append("  No command data available.")

    lines.append("─" * min(width, 72))
    Terminal.help_table(lines)


def clear_command() -> None:
    """Clear the terminal screen."""
    Terminal.clear()


# Lifecycle helpers — used by main.py
def serial_link_command(port: str, baudrate: int = 19200, ping_command_id: int = 0x05) -> MCUSerialLink:
    """Initialize the serial link and perform a startup ping to verify connectivity."""
    startup_ping = encode(
        Command(name="PING", id=ping_command_id, mem=None, address=0, data=None),
        seq=0, multi=False, last=False,
    )
    return MCUSerialLink(port=port, baudrate=baudrate, startup_ping=startup_ping)


def exit_command(serial_link: MCUSerialLink, threads: list) -> None:
    """Cleanly shut down the serial link and any background threads."""
    serial_link.running = False
    serial_link.close()
    for t in threads:
        t.join(timeout=2.0)
    Terminal.success("Debugger closed.")
