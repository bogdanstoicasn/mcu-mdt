from pathlib import Path

from pc_tool import MdtError, command_parser, command_rules, target_model
from pc_tool.commander import (
    Commander,
    clear_command,
    exit_command,
    help_command,
    intro_text,
    serial_link_command,
)
from pc_tool.common.logger import MDTLogger
from pc_tool.common.terminal import Terminal
from pc_tool.event import EventHandler
from pc_tool.parser import CLIHistory, parse_args
from pc_tool.wire_protocol import CommandId


def build_dispatch(specs, serial_link, commander, threads):
    """Build a dispatch dict mapping command names to handler functions."""
    return {
        "EXIT":  lambda cmd: exit_command(serial_link, threads=threads),
        "HELP":  lambda cmd: help_command(specs),
        "CLEAR": lambda cmd: clear_command(),
        "PING":  lambda cmd: commander.ping(cmd),
    }

def setup(build_info_path: str, elf_path: str | None = None):
    """Perform initial setup: load configs, initialize logger, open serial link, start event handlers."""
    try:
        target = target_model.load_target(Path(build_info_path), Path(elf_path) if elf_path else None)
    except MdtError as e:
        MDTLogger.error(f"Cannot load the build: {e}", code=1)
        exit(1)

    MDTLogger.enable_file_logging(mcu=target.mcu)
    MDTLogger.session_start(target.build_info)

    serial_link = serial_link_command(port=target.port, baudrate=target.baudrate, ping_command_id=CommandId.PING)

    try:
        serial_link.open()
    except Exception as e:
        MDTLogger.error(f"Failed to open serial link: {e}", code=1)
        exit(1)

    events = EventHandler(serial_link, uart_idle=target.uart_idle)

    # Drain any stale events that may have accumulated before the event handlers are started.
    events.drain_stale_events()

    threads = events.start()

    commander = Commander(serial_link)

    return target, serial_link, commander, threads


def run_script(script_path: str, target, serial_link, commander, threads):
    """Execute commands from a script file line by line, then exit.

    Blank lines and lines starting with # are skipped.
    Stops on the first command that fails validation or parsing.
    """
    specs    = command_parser.load_specs()
    dispatch = build_dispatch(specs, serial_link, commander, threads)

    MDTLogger.suppress_console()

    try:
        with open(script_path) as f:
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

        try:
            command = command_parser.parse(line, specs, target)
        except command_parser.CommandError as e:
            MDTLogger.error(str(e), code=e.code)
            MDTLogger.error(f"Script aborted: parse error at line {lineno}: {line!r}", code=2)
            break

        if specs[command.name].local:
            MDTLogger.warning(f"Skipping PC-only command at line {lineno}: {command.name}")
            continue

        if command.name in dispatch:
            dispatch[command.name](command)
            continue

        try:
            command_rules.check(command, target)
        except command_parser.CommandError as e:
            MDTLogger.error(str(e), code=e.code)
            MDTLogger.error(f"Script aborted: validation failed at line {lineno}: {line!r}", code=3)
            break

        commander.execute(command)

    MDTLogger.info("Script complete.")
    MDTLogger.restore_console()
    MDTLogger.session_end()


def run_loop(target, serial_link, commander, threads):
    """Main interactive loop: read user input, parse commands, execute them, and print events asynchronously."""
    specs    = command_parser.load_specs()
    dispatch = build_dispatch(specs, serial_link, commander, threads)
    cli      = CLIHistory(completions=list(specs))

    Terminal.intro(intro_text())

    while True:
        try:
            line = cli.input("> ").strip()
            if not line:
                continue

            command = command_parser.parse(line, specs, target)
            if command.name in dispatch:
                dispatch[command.name](command)
                if command.name == "EXIT":
                    break
                continue

            MDTLogger.info(f"Parsed Command: {command}")
            command_rules.check(command, target)
            commander.execute(command)

        except command_parser.CommandError as e:
            MDTLogger.error(str(e), code=e.code)

        except (EOFError, KeyboardInterrupt):
            Terminal.info("Exiting...")
            break

    MDTLogger.session_end()

def main(args=None):
    if args is None:              # console-script entry (mcu-mdt): parse argv here
        args = parse_args()
    target, serial_link, commander, threads = setup(args.build_info, args.elf)

    if args.script:
        run_script(args.script, target, serial_link, commander, threads)
    else:
        run_loop(target, serial_link, commander, threads)


if __name__ == "__main__":
    args = parse_args()
    main(args)
