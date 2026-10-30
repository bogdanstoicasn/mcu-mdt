"""Everything the user sees and types: the prompt, HELP, packets, events, and the log lines.

The pc_tool logger is the one channel for messages. setup_logging() gives it two handlers:

    the log file   every record, as [HH:MM:SS] [LEVEL](code): message
    the console    warnings and errors (ERROR: / WARN:), plus records marked for the user

A record is marked for the user with extra=Console.SHOW (or SUCCESS for an OK: line). An error
code goes in extra={"code": "(N)"}; error_extra(N) builds it. Packets and events are written to
the screen in one write each, and logged as one line.
"""

import logging
import os
import shutil
import sys
import time
from pathlib import Path

from pc_tool import command_parser, wire_protocol

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None

log = logging.getLogger(__name__)

HISTORY_FILE = Path.home() / ".mcu_mdt_history"
_HISTORY_LENGTH = 1000
_BOX_WIDTH = 64
_LOG_FORMAT = "[%(asctime)s] [%(levelname)s]%(code)s: %(message)s"


def error_extra(code: int) -> dict:
    """The extra= for a log call that carries an error code."""
    return {"code": f"({code})"}


class Console:
    SHOW = {"console": ""}              # extra= for an INFO line the user should see
    SUCCESS = {"console": "OK:    "}

    def __init__(self, completions: list[str] = (), history_file: Path = HISTORY_FILE) -> None:
        self.quiet = False              # script mode: nothing on the screen
        self._history_file = history_file
        self._completions = sorted({name.upper() for name in completions})
        if readline:
            self._start_readline()

    # user prompt

    def read_line(self, prompt: str = "> ") -> str:
        return input(prompt)

    def close(self) -> None:
        """Save the history."""
        if readline:
            try:
                readline.write_history_file(str(self._history_file))
            except OSError as exc:      # a read-only home must not stop the shutdown
                log.debug("History not saved: %s", exc)

    def _start_readline(self) -> None:
        readline.set_history_length(_HISTORY_LENGTH)
        if self._history_file.exists():
            try:
                readline.read_history_file(str(self._history_file))
            except OSError as exc:
                log.debug("History not read: %s", exc)
        if not self._completions:
            return
        readline.set_completer(self._complete)
        readline.set_completer_delims(" \t\n")      # the whole first word ("READ_") is matched
        if "libedit" in (readline.__doc__ or ""):    # macOS
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")

    def _complete(self, text: str, state: int) -> str | None:
        """Complete the first word against the command names; arguments are left alone."""
        buffer = readline.get_line_buffer()
        if buffer[:len(buffer) - len(text)].strip():
            return None
        matches = [name for name in self._completions if name.startswith(text.upper())]
        return matches[state] if state < len(matches) else None

    # lines

    def info(self, message: str) -> None:
        log.info("%s", message, extra=self.SHOW)

    def success(self, message: str) -> None:
        log.info("%s", message, extra=self.SUCCESS)

    def intro(self) -> None:
        width = shutil.get_terminal_size().columns
        lines = ["MCU-MDT - Microcontroller Memory Debug Tool", "---------------------------------------",
                 "Type 'HELP' to see available commands."]
        self._write("\n" + "\n".join(line.center(width) for line in lines) + "\n\n")

    def help(self, specs: dict[str, command_parser.CommandSpec]) -> None:
        rule = "─" * min(shutil.get_terminal_size().columns, 72)
        usage_width = 32
        lines = [rule, "  MCU-MDT — Available Commands", rule]
        for spec in specs.values():
            usage = f"  {spec.usage}"
            if len(usage) < usage_width:
                lines.append(f"{usage.ljust(usage_width)}{spec.description}")
            else:
                lines += [usage, f"{'':<{usage_width}}{spec.description}"]
        lines.append(rule)
        self._write("\n" + "\n".join(lines) + "\n\n")

    def clear(self) -> None:
        if not self.quiet:
            os.system("cls" if os.name == "nt" else "clear")

    def event(self, event: wire_protocol.Event) -> None:
        """Print the event over the prompt, then redraw the prompt and the half-typed line."""
        line = event.describe()
        if not self.quiet:
            typed = readline.get_line_buffer() if readline else ""
            sys.stdout.write(f"\r\033[K{line}\n> {typed}")
            sys.stdout.flush()
        log.info("[event] %s", line)

    def packet(self, packet: wire_protocol.Packet) -> None:
        self._write(_packet_box(packet))
        log.info("Received packet: %s", packet)

    def _write(self, text: str) -> None:
        if not self.quiet:
            sys.stdout.write(text)


class ConsoleHandler(logging.Handler):
    """Shows warnings, errors and the records marked for the user."""

    def __init__(self, console: Console) -> None:
        super().__init__(logging.INFO)
        self._console = console

    def emit(self, record: logging.LogRecord) -> None:
        if self._console.quiet:
            return
        try:
            message = record.getMessage()
            if record.levelno >= logging.WARNING:
                code = getattr(record, "code", "")
                prefix = "ERROR: " if record.levelno >= logging.ERROR else "WARN:  "
                sys.stdout.write(f"{prefix}{message}{' ' + code if code else ''}\n")
            elif hasattr(record, "console"):
                sys.stdout.write(f"{record.console}{message}\n")
        except Exception:               # logging must never raise into the caller
            self.handleError(record)


def setup_logging(console: Console) -> None:
    """The console handler on the pc_tool logger; every module logs through it."""
    logger = logging.getLogger("pc_tool")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(ConsoleHandler(console))


def start_log_file(mcu: str, log_dir: str = "logs") -> str:
    """Log everything to logs/mdt_<mcu>_<date>_<time>.log as well; returns its path."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"mdt_{mcu}_{time.strftime('%Y%m%d_%H%M%S')}.log")
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%H:%M:%S", defaults={"code": ""}))
    logging.getLogger("pc_tool").addHandler(handler)
    return path


def _packet_box(packet: wire_protocol.Packet) -> str:
    try:
        command = f"{wire_protocol.CommandId(packet.cmd_id).name} (0x{packet.cmd_id:02X})"
    except ValueError:
        command = f"<unknown> (0x{packet.cmd_id:02X})"
    names = [flag.name for flag in wire_protocol.Flag if packet.flags & flag]
    if packet.is_event:
        status = "[EVENT]"
    elif packet.is_ack:
        status = "[NACK]" if packet.is_error else "[ACK]"
    else:
        status = "[COMMAND]"
    mem = f"0x{packet.mem_id:02X} ({packet.mem_id})" if packet.mem_id is not None else "<not present>"
    lines = [
        "┌─ Received Packet " + "─" * (_BOX_WIDTH - 19),
        f"│  Status   : {status}",
        f"│  Command  : {command}",
        f"│  Flags    : 0x{packet.flags:02X}  {' | '.join(names) if names else '<none>'}",
        f"│  Sequence : {packet.seq}",
        f"│  Mem ID   : {mem}",
        f"│  Address  : 0x{packet.address:08X}",
        f"│  Length   : {packet.length}",
        f"│  Data     : {' '.join(f'{b:02X}' for b in packet.data)}",
        f"│  CRC      : 0x{packet.crc:04X}",
        f"│  raw      : {packet.raw.hex()}",
        "└" + "─" * (_BOX_WIDTH - 1),
    ]
    return "\n".join(lines) + "\n"
