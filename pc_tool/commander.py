import os
from common.dataclasses import Command
from common.protocol import serialize_command_packet, validate_command_packet
from common.uart_io import MCUSerialLink
from common.enums import FenceType, UtilEnum

def intro_text():

    intro_string = """
MCU-MDT - Microcontroller Memory Debug Tool
---------------------------------------
Type 'HELP' to see available commands.
"""

    return intro_string

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
    PING                Send a ping command to the connected MCU.
"""
    print(help_text)

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

def ping_command(command: Command, yaml_build_data=None, serial_link: MCUSerialLink = None):
    byte_packet = serialize_command_packet(command, seq=0, multi=False, last=False)  # seq can be 0 for ping command
    print(f"Serialized Ping Command Packet: {byte_packet.hex()}")
    ack = serial_link.send_packet(byte_packet)
    print(f"Ping command sent. Echoed {len(ack)} bytes: {ack.hex()}")
    if validate_command_packet(ack):
        print("Command packet validation successful.")

def execute_command(command: Command, serial_link: MCUSerialLink = None):
    if command.data is None or len(command.data) == 0:
        # No data, just a single packet
        byte_packet = serialize_command_packet(command, seq=0, multi=False, last=False)  # seq can be 0 for simple commands
        print(f"Serialized Command Packet: {byte_packet.hex()}")
        if serial_link:
            ack = serial_link.send_packet(byte_packet)
            print(f"Received ACK: {ack.hex() if ack else 'No response'}")
            if validate_command_packet(ack):
                print("Command packet validation successful.")
        return

    seq = 0

    # Split data into 4-byte chunks
    for i in range(0, len(command.data), 4):
        chunk = command.data[i:i+4]
        if len(chunk) != 4:
            # Pad the last chunk with zeros if needed (optional)
            chunk = chunk.ljust(4, b'\x00')

        # Create a new command packet for this chunk
        chunk_command = Command(
            name=command.name,
            id=command.id,
            mem=command.mem,
            address=command.address + i,  # increment address
            data=chunk
        )

        byte_packet = serialize_command_packet(chunk_command, seq=seq, multi=True, last=(i + 4 >= len(command.data)))
        print(f"Serialized Command Packet: {byte_packet.hex()}")
        if serial_link:
            ack = serial_link.send_packet(byte_packet)
            print(f"Received ACK: {ack.hex() if ack else 'No response'}")

        seq  = (seq + 1) % 0xFF  # Increment sequence number, wrap around at 256
