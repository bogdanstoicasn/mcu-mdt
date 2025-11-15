from common.dataclasses import Command

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
  READ <mem_type> <address> <length>
                      Read data from specified memory type and address.
  WRITE <mem_type> <address> <data>
                      Write data to specified memory type and address.
"""
    print(help_text)

def execute_command(command: Command):
    pass