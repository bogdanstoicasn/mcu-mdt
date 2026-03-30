import os
import shutil
from pc_tool.common.dataclasses import Command
from pc_tool.common.protocol import serialize_command_packet, validate_command_packet, is_nack_packet
from pc_tool.common.uart_io import MCUSerialLink
from pc_tool.common.enums import UtilEnum, MDTOffset
from pc_tool.common.logger import MDTLogger
from pc_tool.parser import parse_packet

def intro_text():
    width = shutil.get_terminal_size().columns
    
    lines = [
        "MCU-MDT - Microcontroller Memory Debug Tool",
        "---------------------------------------",
        "Type 'HELP' to see available commands."
    ]
    
    return "\n" + "\n".join(line.center(width) for line in lines) + "\n"

def help_command(command_data: dict = None):
    import shutil

    width = shutil.get_terminal_size().columns
    col1  = 32  # width of the command + usage column

    # type → human readable hint (fallback if no explicit hint in yaml)
    type_hints = {
        "uint32":        "<addr>",
        "uint32_or_str": "<addr|reg>",
        "uint16":        "<value>",
        "uint8":         "<value>",
        "str":           "<control>",
        "bytes":         "<hex>",
    }

    lines = []
    lines.append("─" * min(width, 72))
    lines.append("  MCU-MDT — Available Commands")
    lines.append("─" * min(width, 72))

    if command_data:
        commands = command_data.get("commands", {})
        for name, info in commands.items():
            params = info.get("params", [])
            description = info.get("description", "")

            param_str = " ".join(
                p.get("hint") or type_hints.get(p["type"], f"<{p['name']}>")
                for p in params
            )

            usage = f"  {name}"
            if param_str:
                usage += f" {param_str}"

            # pad or wrap if usage line is too long
            if len(usage) < col1:
                usage = usage.ljust(col1)
                lines.append(f"{usage}{description}")
            else:
                lines.append(usage)
                lines.append(f"{''.ljust(col1)}{description}")
    else:
        lines.append("  No command data available.")

    lines.append("─" * min(width, 72))
    MDTLogger.info("\n" + "\n".join(lines) + "\n")

def serial_link_command(port: str, baudrate: int = 19200, ping_command_id: int = 0x05) -> MCUSerialLink:
    """
    Creates and returns an MCUSerialLink instance for the given port and baudrate.
    """
    
    # We create here the startup ping to synchronize with the MCU
    startup_ping_command = Command(
        name="PING",
        id=ping_command_id,
        mem=None,
        address=0,
        data=None
    )
    startup_ping_packet = serialize_command_packet(startup_ping_command, seq=0, multi=False, last=False)  # seq can be 0 for startup ping

    serial_link = MCUSerialLink(
        port=port,
        baudrate=baudrate,
        startup_ping=startup_ping_packet
    )

    return serial_link


def clear_command():
    os.system('cls' if os.name == 'nt' else 'clear')

def exit_command(serial_link: MCUSerialLink, threads: list):
    MDTLogger.info("Exiting...")

    # stop worker loops
    serial_link.running = False

    # close UART
    serial_link.close()

    # wait for event thread to exit
    for t in threads:
        t.join(timeout=2.0)

    MDTLogger.info("Debugger closed.")

def ping_command(command: Command, yaml_build_data=None, serial_link: MCUSerialLink = None):
    byte_packet = serialize_command_packet(command, seq=0, multi=False, last=False)

    MDTLogger.info(f"Serialized Ping Command Packet: {byte_packet.hex()}")

    for attempt in range(1, UtilEnum.MDT_MAX_RETRIES + 1):
        serial_link.send_packet(byte_packet)

        ack = serial_link.get_response_packet()

        if ack is None:
            MDTLogger.warning(f"No response from MCU (attempt {attempt}/{UtilEnum.MDT_MAX_RETRIES}).")
            continue

        if is_nack_packet(ack):
            MDTLogger.warning(f"NACK received for ping (attempt {attempt}/{UtilEnum.MDT_MAX_RETRIES}), retrying...")
            continue

        MDTLogger.info(f"Received ACK: {ack.hex()}")
        parse_packet(ack)

        if validate_command_packet(ack):
            MDTLogger.info("Command packet validation successful.")
        return

    MDTLogger.error(f"Ping failed after {UtilEnum.MDT_MAX_RETRIES} attempts.", code=4)

def execute_command(command: Command, serial_link: MCUSerialLink = None):

    seq = 0
    is_write = command.data is not None

    length = command.length if command.length is not None else UtilEnum.WORD_SIZE

    for i in range(0, length, UtilEnum.WORD_SIZE):

        chunk_length = min(UtilEnum.WORD_SIZE, length - i)

        if is_write:
            chunk = command.data[i:i + chunk_length]
            if len(chunk) != UtilEnum.WORD_SIZE:
                chunk = chunk.ljust(UtilEnum.WORD_SIZE, b'\x00')
        else:
            chunk = None

        chunk_command = Command(
            name=command.name,
            id=command.id,
            mem=command.mem,
            address=command.address + i,
            length=chunk_length,
            data=chunk
        )

        byte_packet = serialize_command_packet(
            chunk_command,
            seq=seq,
            multi=(length > UtilEnum.WORD_SIZE),
            last=(i + UtilEnum.WORD_SIZE >= length)
        )

        MDTLogger.info(f"Serialized Command Packet: {byte_packet.hex()}")

        if serial_link:
            ack = None
            for attempt in range(1, UtilEnum.MDT_MAX_RETRIES + 1):
                serial_link.send_packet(byte_packet)

                ack = serial_link.get_response_packet()

                if ack is None:
                    MDTLogger.warning(
                        f"No response from MCU for seq={seq} "
                        f"(attempt {attempt}/{UtilEnum.MDT_MAX_RETRIES})."
                    )
                    continue

                if is_nack_packet(ack):
                    nack_seq = ack[MDTOffset.SEQ]
                    MDTLogger.warning(
                        f"NACK received for seq={nack_seq} "
                        f"(attempt {attempt}/{UtilEnum.MDT_MAX_RETRIES}), retrying..."
                    )
                    ack = None
                    continue

                break  # got a valid (non-NACK) response

            if ack is None:
                MDTLogger.error(
                    f"Command failed after {UtilEnum.MDT_MAX_RETRIES} attempts "
                    f"(seq={seq}). Aborting.",
                    code=4
                )
                return

            MDTLogger.info(f"Received ACK: {ack.hex()}")
            parse_packet(ack)

            if validate_command_packet(ack):
                MDTLogger.info("Command packet validation successful.")

        seq = (seq + 1) % 0xFF
