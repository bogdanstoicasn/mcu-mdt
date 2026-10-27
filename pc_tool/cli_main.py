"""The mcu-mdt command: load the build, connect, run the session, shut down cleanly.

    mcu-mdt build/<part>/build_info.yaml [--elf firmware.elf] [--script commands.txt]

Exit status: 0 when the session ended normally, 1 when it could not start or a script stopped
at an error.
"""

import _thread
import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from pc_tool import (
    MdtError,
    command_client,
    command_parser,
    debug_session,
    event_pump,
    serial_link,
    target_model,
    user_console,
    wire_protocol,
)

log = logging.getLogger(__name__)

_STARTUP_PING = wire_protocol.encode(wire_protocol.Command(name="PING", id=wire_protocol.CommandId.PING))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mcu-mdt", description="MCU MDT Debugger CLI")
    parser.add_argument("build_info", help="Path to build_info.yaml file")
    parser.add_argument("--elf", default=None,
                        help="The firmware you flashed (default: the elf named in build_info.yaml, e.g. your "
                             "project's mcu_mdt_user.elf instead of the example)")
    parser.add_argument("--script", default=None,
                        help="Path to a script file with commands to execute (exits after completion)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    specs = command_parser.load_specs()
    console = user_console.Console(completions=list(specs))
    user_console.setup_logging(console)

    try:
        target = target_model.load_target(Path(args.build_info), Path(args.elf) if args.elf else None)
    except MdtError as exc:
        log.error("Cannot load the build: %s", exc, extra=user_console.error_extra(1))
        return 1

    log_file = user_console.start_log_file(target.mcu)
    _session_banner("MCU-MDT SESSION START", target, log_file)
    try:
        return _connect_and_run(args, target, specs, console)
    finally:
        console.close()
        _session_banner("MCU-MDT SESSION END")


def _connect_and_run(args: argparse.Namespace, target: target_model.Target,
                     specs: dict[str, command_parser.CommandSpec], console: user_console.Console) -> int:
    link = serial_link.SerialLink(target.port, target.baudrate)
    try:
        link.open()
    except serial_link.LinkError as exc:
        log.error("Failed to open serial link: %s", exc, extra=user_console.error_extra(1))
        return 1
    link.sync(_STARTUP_PING)

    pump = event_pump.EventPump(link, target.uart_idle, on_event=console.event, on_lost=_interrupt_main)
    pump.drain_stale_events()           # events left from an earlier session, before the reader starts
    pump.start()
    console.info("UART idle interrupt mode — event poll thread started." if target.uart_idle
                 else "Poll mode — MCU drains events via mcu_mdt_poll(), no event poll thread needed.")

    session = debug_session.DebugSession(target, specs, command_client.CommandClient(link), console)
    ok = False
    try:
        if args.script:
            console.quiet = True
            ok = session.run_script(args.script)
        else:
            session.repl()
            ok = True
    except KeyboardInterrupt:           # Ctrl-C during a command, or the link was lost
        console.info("Exiting...")
    finally:
        pump.stop()
        link.close()
        console.success("Debugger closed.")
    return 0 if ok and not pump.lost else 1


def _session_banner(title: str, target: target_model.Target | None = None, log_file: str | None = None) -> None:
    """The log file's header or footer (file only: these records are not marked for the console)."""
    lines = ["=" * 60, title]
    if target is not None:
        info = target.build_info
        lines += [f"  MCU      : {info.get('mcu', 'unknown')}", f"  Platform : {info.get('platform', 'unknown')}",
                  f"  Port     : {info.get('port', 'unknown')}", f"  Baudrate : {info.get('baudrate', 19200)}",
                  f"  Log file : {log_file or 'none'}"]
    for line in lines + ["=" * 60]:
        log.info("%s", line)


def _interrupt_main() -> None:
    """The link is gone: wake the main thread out of input() with KeyboardInterrupt, so it shuts down cleanly."""
    if hasattr(signal, "pthread_kill"):
        signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)
    else:                               # Windows: takes effect at the next line typed
        _thread.interrupt_main()


if __name__ == "__main__":
    sys.exit(main())
