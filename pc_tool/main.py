from pc_tool.loader import ConfigLoader
from pc_tool.parser import parse_line, parse_args, CLIHistory
from pc_tool.commander import execute_command, help_command, intro_text, clear_command, ping_command, serial_link_command, exit_command
from pc_tool.validator import validate_commands
from pc_tool.event import start_async_handlers
from pc_tool.common.logger import MDTLogger


def build_dispatch(loader, serial_link, threads):
    return {
        "EXIT":  lambda cmd: exit_command(serial_link, threads=threads),
        "HELP":  lambda cmd: help_command(loader.yaml_command_data),
        "CLEAR": lambda cmd: clear_command(),
        "PING":  lambda cmd: ping_command(cmd, loader.yaml_build_data, serial_link),
    }

def setup(build_info_path: str):
    loader = ConfigLoader(build_info_path)

    MDTLogger.enable_file_logging(mcu=loader.yaml_build_data.get('mcu', 'unknown'))
    MDTLogger.session_start(loader.yaml_build_data)

    serial_link = serial_link_command(
        port=loader.yaml_build_data['port'],
        baudrate=loader.yaml_build_data.get('baudrate', 19200),
        ping_command_id=loader.yaml_command_data['commands']['PING']['id']
    )

    try:
        serial_link.open()
    except Exception as e:
        MDTLogger.error(f"Failed to open serial link: {e}", code=1)
        exit(1)

    threads = start_async_handlers(serial_link)

    return loader, serial_link, threads

def run_loop(loader, serial_link, threads):
    cli      = CLIHistory()
    commands = loader.yaml_command_data['commands']
    control  = loader.yaml_command_data['control_values']
    metadata = loader.mcu_metadata
    dispatch = build_dispatch(loader, serial_link, threads)

    MDTLogger.info(intro_text())

    while True:
        try:
            line = cli.input("> ").strip()
            if not line:
                continue

            command = parse_line(line, commands, control, metadata)
            if not command:
                MDTLogger.error("Invalid command or parsing error.", code=2)
                continue

            if command.name in dispatch:
                dispatch[command.name](command)
                if command.name == "EXIT":
                    break
                continue

            MDTLogger.info(f"Parsed Command: {command}")

            if not validate_commands(command, metadata):
                MDTLogger.error("Command validation failed.", code=3)
                continue

            execute_command(command, serial_link)

        except (EOFError, KeyboardInterrupt):
            MDTLogger.info("Exiting...")
            break

    MDTLogger.session_end()

def main(args):
    loader, serial_link, threads = setup(args.build_info)
    run_loop(loader, serial_link, threads)

if __name__ == "__main__":
    args = parse_args()
    main(args)