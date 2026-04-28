from pc_tool.loader import ConfigLoader
from pc_tool.parser import parse_line, parse_args, CLIHistory
from pc_tool.commander import Commander, help_command, intro_text, clear_command, serial_link_command, exit_command
from pc_tool.validator import validate_commands
from pc_tool.event import start_async_handlers
from pc_tool.common.logger import MDTLogger


def build_dispatch(loader, serial_link, commander, threads):
    return {
        "EXIT":  lambda cmd: exit_command(serial_link, threads=threads),
        "HELP":  lambda cmd: help_command(loader.yaml_command_data),
        "CLEAR": lambda cmd: clear_command(),
        "PING":  lambda cmd: commander.ping(cmd),
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

    threads = start_async_handlers(
        serial_link,
        uart_idle=bool(loader.yaml_build_data.get('uart_idle', False))
    )

    commander = Commander(serial_link)

    return loader, serial_link, commander, threads


def run_script(script_path: str, loader, serial_link, commander, threads):
    """Execute commands from a script file line by line, then exit.

    Blank lines and lines starting with # are skipped.
    Stops on the first command that fails validation or parsing.
    """
    commands = loader.yaml_command_data['commands']
    control  = loader.yaml_command_data['control_values']
    metadata = loader.mcu_metadata
    symbols  = loader.elf_symbols
    dispatch = build_dispatch(loader, serial_link, commander, threads)

    MDTLogger.suppress_console()

    try:
        with open(script_path, 'r') as f:
            lines = f.readlines()
    except OSError as e:
        MDTLogger.error(f"Cannot open script file: {e}", code=1)
        MDTLogger.restore_console()
        MDTLogger.session_end()
        return

    MDTLogger.info(f"Running script: {script_path} ({len(lines)} lines)")

    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()

        if not line or line.startswith('#'):
            continue

        MDTLogger.info(f"[{lineno}] {line}")

        command = parse_line(line, commands, control, metadata, symbols)
        if not command:
            MDTLogger.error(f"Script aborted: parse error at line {lineno}: {line!r}", code=2)
            break

        if command.name in ('EXIT', 'HELP', 'CLEAR'):
            MDTLogger.warning(f"Skipping PC-only command at line {lineno}: {command.name}")
            continue

        if command.name in dispatch:
            dispatch[command.name](command)
            continue

        if not validate_commands(command, metadata):
            MDTLogger.error(f"Script aborted: validation failed at line {lineno}: {line!r}", code=3)
            break

        commander.execute(command)

    MDTLogger.info("Script complete.")
    MDTLogger.restore_console()
    MDTLogger.session_end()


def run_loop(loader, serial_link, commander, threads):
    cli      = CLIHistory()
    commands = loader.yaml_command_data['commands']
    control  = loader.yaml_command_data['control_values']
    metadata = loader.mcu_metadata
    symbols  = loader.elf_symbols
    dispatch = build_dispatch(loader, serial_link, commander, threads)

    MDTLogger.info(intro_text())

    while True:
        try:
            line = cli.input("> ").strip()
            if not line:
                continue

            command = parse_line(line, commands, control, metadata, symbols)
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

            commander.execute(command)

        except (EOFError, KeyboardInterrupt):
            MDTLogger.info("Exiting...")
            break

    MDTLogger.session_end()

def main(args):
    loader, serial_link, commander, threads = setup(args.build_info)

    if args.script:
        run_script(args.script, loader, serial_link, commander, threads)
    else:
        run_loop(loader, serial_link, commander, threads)


if __name__ == "__main__":
    args = parse_args()
    main(args)