import os
from common.dataclasses import Command
from common.protocol import serialize_command_packet
from common.uart_io import send_packet_to_mcu

def intro_text():

    intro_string = """
PC Tool Command Line Interface
==========================
Connect the device. If already connected, disconnect and reconnect.
Type HELP for available commands.
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

def clear_command():
    os.system('cls' if os.name == 'nt' else 'clear')

def ping_command(command: Command, yaml_build_data=None):
    byte_packet = serialize_command_packet(command)
    print(f"Serialized PING Command Packet: {byte_packet.hex()}")
    send_packet_to_mcu(byte_packet=byte_packet, port=yaml_build_data['port'])

def execute_command(command: Command):
    if command.data is None or len(command.data) == 0:
        # No data, just a single packet
        byte_packet = serialize_command_packet(command)
        print(f"Serialized Command Packet: {byte_packet.hex()}")
        return

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

        byte_packet = serialize_command_packet(chunk_command)
        print(f"Serialized Command Packet: {byte_packet.hex()}")
        # Here you would actually send byte_packet over UART
