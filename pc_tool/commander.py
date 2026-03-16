import os
import shutil
from common.dataclasses import Command
from common.protocol import serialize_command_packet, validate_command_packet
from common.uart_io import MCUSerialLink
from common.enums import UtilEnum
from common.logger import MDTLogger
from parser import parse_packet

def intro_text():
    width = shutil.get_terminal_size().columns
    
    lines = [
        "MCU-MDT - Microcontroller Memory Debug Tool",
        "---------------------------------------",
        "Type 'HELP' to see available commands."
    ]
    
    return "\n" + "\n".join(line.center(width) for line in lines) + "\n"

def help_command():
    help_text = """
Available Commands:
    HELP                Show this help message.
    EXIT                Exit the command line interface.
    READ_MEM <mem_type> <address> <length>
                      Read data from specified memory type and address.
    WRITE_MEM <mem_type> <address> <length> <data>
                      Write data to specified memory type and address.
    READ_REG <register_address>
                        Read data from specified register address.
    WRITE_REG <register_address> <data>
                        Write data to specified register address.
    BREAKPOINT <id> <operation>
                        Software breakpoint management. Operation can be 'ENABLED', 'DISABLED', 'NEXT', 'RESET'.
    PING                Send a ping command to the connected MCU.
"""
    MDTLogger.info(help_text)

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

    serial_link.send_packet(byte_packet)

    ack = serial_link.get_response_packet()

    if not ack:
        MDTLogger.error("No response from MCU.", code=4)
        return

    MDTLogger.info(f"Received ACK: {ack.hex()}")
    parse_packet(ack)

    if validate_command_packet(ack):
        MDTLogger.info("Command packet validation successful.")

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

            serial_link.send_packet(byte_packet)

            ack = serial_link.get_response_packet()

            if not ack:
                MDTLogger.error("No response from MCU.", code=4)
                return

            MDTLogger.info(f"Received ACK: {ack.hex()}")
            parse_packet(ack)

            if validate_command_packet(ack):
                MDTLogger.info("Command packet validation successful.")

        seq = (seq + 1) % 0xFF
