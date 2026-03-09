from loader import ConfigLoader
from parser import parse_line, parse_args, CLIHistory
from commander import execute_command, help_command, intro_text, clear_command, ping_command, serial_link_command, exit_command
from validator import validate_commands
from event import start_async_handlers
from common.logger import MDTLogger

if __name__ == "__main__":
    args = parse_args()

    build_info_path = args.build_info

    loader = ConfigLoader(build_info_path)

    cli = CLIHistory()

    commands = loader.yaml_command_data['commands']

    mem_types = loader.yaml_command_data['mem_types']

    mcu_metadata = loader.mcu_metadata

    # Start the connection to the MCU
    serial_link = serial_link_command(
        port=loader.yaml_build_data['port'],
        baudrate=loader.yaml_build_data.get('baudrate', 19200),
        ping_command_id=commands['PING']['id']
    )
    try:
        serial_link.open()
    except Exception as e:
        MDTLogger.error(f"Failed to open serial link: {e}", code=1)
        exit(1)
    
    rx_thread, event_thread = start_async_handlers(serial_link)

    MDTLogger.info(intro_text(), code=0)

    while True:
        try:
            line = cli.input("> ").strip()
            if not line:
                continue

            command = parse_line(line, commands, mem_types)

            if not command:
                MDTLogger.error("Invalid command or parsing error.", code=2)
                continue

            # Handle the CLI commands(EXIT, HELP) directly here
            if command.name == "EXIT":
                exit_command(serial_link, threads=[rx_thread, event_thread])
                break
            elif command.name == "HELP":
                help_command()
                continue
            elif command.name == "CLEAR":
                clear_command()
                continue
            elif command.name == "PING":
                ping_command(command, loader.yaml_build_data, serial_link)
                continue


            MDTLogger.info(f"Parsed Command: {command}", code=0)

            if not validate_commands(command, mcu_metadata):
                MDTLogger.error("Command validation failed.", code=3)
                continue

            execute_command(command, serial_link)
        except EOFError as end_of_file:
            MDTLogger.info("Exiting...", code=0)
            break
        except KeyboardInterrupt as keyboard_interrupt:
            MDTLogger.info("Exiting with keyboard interrupt...", code=0)
            break