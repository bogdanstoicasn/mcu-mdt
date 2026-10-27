import _thread
import signal
import threading
from pathlib import Path

from pc_tool import (
    MdtError,
    command_client,
    command_parser,
    command_rules,
    event_pump,
    serial_link,
    target_model,
    wire_protocol,
)
from pc_tool.commander import clear_command, exit_command, help_command, intro_text
from pc_tool.common.logger import MDTLogger
from pc_tool.common.terminal import Terminal
from pc_tool.parser import CLIHistory, parse_args

_STARTUP_PING = wire_protocol.encode(wire_protocol.Command(name="PING", id=wire_protocol.CommandId.PING))


def build_dispatch(specs, link, pump):
    """The local commands: they never leave the PC."""
    return {
        "EXIT":  lambda cmd: exit_command(link, pump),
        "HELP":  lambda cmd: help_command(specs),
        "CLEAR": lambda cmd: clear_command(),
    }


def execute(client, command) -> None:
    """Send *command* and show every reply it got."""
    try:
        replies = client.run(command)
    except command_client.NoReplyError as e:
        replies = e.replies
        MDTLogger.error(str(e), code=e.code)
    for reply in replies:
        Terminal.packet(reply, raw=reply.raw)


def _interrupt_main() -> None:
    """The link is gone: wake the main thread out of input() with KeyboardInterrupt, so it shuts down cleanly."""
    if hasattr(signal, "pthread_kill"):
        signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)
    else:                                   # Windows: takes effect at the next line typed
        _thread.interrupt_main()

def setup(build_info_path: str, elf_path: str | None = None):
    """Perform initial setup: load configs, initialize logger, open serial link, start event handlers."""
    try:
        target = target_model.load_target(Path(build_info_path), Path(elf_path) if elf_path else None)
    except MdtError as e:
        MDTLogger.error(f"Cannot load the build: {e}", code=1)
        exit(1)

    MDTLogger.enable_file_logging(mcu=target.mcu)
    MDTLogger.session_start(target.build_info)

    link = serial_link.SerialLink(target.port, target.baudrate)
    try:
        link.open()
    except serial_link.LinkError as e:
        MDTLogger.error(f"Failed to open serial link: {e}", code=1)
        exit(1)
    link.sync(_STARTUP_PING)

    pump = event_pump.EventPump(link, target.uart_idle, on_event=lambda e: Terminal.event(e.describe()),
                                on_lost=_interrupt_main)
    pump.drain_stale_events()       # events left from an earlier session, before the reader starts
    pump.start()
    if target.uart_idle:
        Terminal.info("UART idle interrupt mode — event poll thread started.")
    else:
        Terminal.info("Poll mode — MCU drains events via mcu_mdt_poll(), no event poll thread needed.")

    return target, link, pump, command_client.CommandClient(link)


def run_script(script_path: str, target, link, pump, client):
    """Execute commands from a script file line by line, then exit.

    Blank lines and lines starting with # are skipped.
    Stops on the first command that fails validation or parsing.
    """
    specs = command_parser.load_specs()

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

        try:
            command_rules.check(command, target)
        except command_parser.CommandError as e:
            MDTLogger.error(str(e), code=e.code)
            MDTLogger.error(f"Script aborted: validation failed at line {lineno}: {line!r}", code=3)
            break

        execute(client, command)

    MDTLogger.info("Script complete.")
    MDTLogger.restore_console()
    MDTLogger.session_end()


def run_loop(target, link, pump, client):
    """Main interactive loop: read user input, parse commands, execute them, and print events asynchronously."""
    specs    = command_parser.load_specs()
    dispatch = build_dispatch(specs, link, pump)
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
            execute(client, command)

        except command_parser.CommandError as e:
            MDTLogger.error(str(e), code=e.code)

        except (EOFError, KeyboardInterrupt):
            Terminal.info("Exiting...")
            break

    MDTLogger.session_end()

def main(args=None):
    if args is None:              # console-script entry (mcu-mdt): parse argv here
        args = parse_args()
    session = setup(args.build_info, args.elf)
    try:
        if args.script:
            run_script(args.script, *session)
        else:
            run_loop(*session)
    except KeyboardInterrupt:           # the link was lost mid-script
        Terminal.info("Exiting...")
        MDTLogger.session_end()


if __name__ == "__main__":
    args = parse_args()
    main(args)
