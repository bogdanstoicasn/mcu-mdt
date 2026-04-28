import os
import shutil

from pc_tool.common.dataclasses import Command
from pc_tool.common.protocol import serialize_command_packet, validate_command_packet, is_nack_packet
from pc_tool.common.uart_io import MCUSerialLink
from pc_tool.common.enums import UtilEnum, MDTOffset
from pc_tool.common.logger import MDTLogger
from pc_tool.parser import parse_packet


# ---------------------------------------------------------------------------
# Commander — owns serial_link, handles all protocol operations
# ---------------------------------------------------------------------------

class Commander:
    """Sends commands to the MCU and handles ACK/NACK/retry logic.

    Usage::

        commander = Commander(serial_link)
        commander.ping(ping_cmd)
        commander.execute(write_cmd)
    """

    def __init__(self, serial_link: MCUSerialLink) -> None:
        self._link = serial_link

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_with_retry(self, packet: bytes, seq: int) -> bytes | None:
        """Send a packet and retry up to MDT_MAX_RETRIES times.

        Returns the ACK packet on success, or None if all attempts fail.
        """
        for attempt in range(1, UtilEnum.MDT_MAX_RETRIES + 1):
            self._link.send_packet(packet)
            ack = self._link.get_response_packet()

            if ack is None:
                MDTLogger.warning(
                    f"No response from MCU for seq={seq} "
                    f"(attempt {attempt}/{UtilEnum.MDT_MAX_RETRIES})."
                )
                continue

            if is_nack_packet(ack):
                MDTLogger.warning(
                    f"NACK received for seq={ack[MDTOffset.SEQ]} "
                    f"(attempt {attempt}/{UtilEnum.MDT_MAX_RETRIES}), retrying..."
                )
                continue

            return ack

        return None

    @staticmethod
    def _log_ack(ack: bytes) -> None:
        MDTLogger.info(f"Received ACK: {ack.hex()}")
        parse_packet(ack)
        if validate_command_packet(ack):
            MDTLogger.info("Command packet validation successful.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ping(self, command: Command) -> None:
        packet = serialize_command_packet(command, seq=0, multi=False, last=False)
        MDTLogger.info(f"Serialized Ping Command Packet: {packet.hex()}")

        ack = self._send_with_retry(packet, seq=0)
        if ack is None:
            MDTLogger.error(f"Ping failed after {UtilEnum.MDT_MAX_RETRIES} attempts.", code=4)
            return

        self._log_ack(ack)

    def execute(self, command: Command) -> None:
        """Send a command, splitting into word-sized chunks if needed."""
        is_write = command.data is not None
        length   = command.length if command.length is not None else UtilEnum.WORD_SIZE
        seq      = 0

        for offset in range(0, length, UtilEnum.WORD_SIZE):
            chunk_length = min(UtilEnum.WORD_SIZE, length - offset)

            if is_write:
                chunk = command.data[offset : offset + chunk_length]
                if len(chunk) != UtilEnum.WORD_SIZE:
                    chunk = chunk.ljust(UtilEnum.WORD_SIZE, b'\x00')
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

            packet = serialize_command_packet(
                chunk_cmd,
                seq   = seq,
                multi = length > UtilEnum.WORD_SIZE,
                last  = offset + UtilEnum.WORD_SIZE >= length,
            )

            MDTLogger.info(f"Serialized Command Packet: {packet.hex()}")

            ack = self._send_with_retry(packet, seq=seq)
            if ack is None:
                MDTLogger.error(
                    f"Command failed after {UtilEnum.MDT_MAX_RETRIES} attempts "
                    f"(seq={seq}). Aborting.",
                    code=4,
                )
                return

            self._log_ack(ack)
            seq = (seq + 1) % 0xFF


# ---------------------------------------------------------------------------
# UI helpers — stateless, no class needed
# ---------------------------------------------------------------------------

def intro_text() -> str:
    width = shutil.get_terminal_size().columns
    lines = [
        "MCU-MDT - Microcontroller Memory Debug Tool",
        "---------------------------------------",
        "Type 'HELP' to see available commands.",
    ]
    return "\n" + "\n".join(line.center(width) for line in lines) + "\n"


def help_command(command_data: dict = None) -> None:
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
    MDTLogger.info("\n" + "\n".join(lines) + "\n")


def clear_command() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')


# ---------------------------------------------------------------------------
# Lifecycle helpers — used by main.py
# ---------------------------------------------------------------------------

def serial_link_command(port: str, baudrate: int = 19200, ping_command_id: int = 0x05) -> MCUSerialLink:
    startup_ping = serialize_command_packet(
        Command(name="PING", id=ping_command_id, mem=None, address=0, data=None),
        seq=0, multi=False, last=False,
    )
    return MCUSerialLink(port=port, baudrate=baudrate, startup_ping=startup_ping)


def exit_command(serial_link: MCUSerialLink, threads: list) -> None:
    MDTLogger.info("Exiting...")
    serial_link.running = False
    serial_link.close()
    for t in threads:
        t.join(timeout=2.0)
    MDTLogger.info("Debugger closed.")


# ---------------------------------------------------------------------------
# Module-level shims — preserve existing call sites in main.py and tests
# ---------------------------------------------------------------------------

def ping_command(command: Command, yaml_build_data=None, serial_link: MCUSerialLink = None) -> None:
    Commander(serial_link).ping(command)


def execute_command(command: Command, serial_link: MCUSerialLink = None) -> None:
    Commander(serial_link).execute(command)