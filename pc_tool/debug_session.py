"""One debug session on a connected MCU: every line, typed or scripted, takes the same path.

    parse (command_parser) -> check (command_rules) -> send (command_client) -> show (user_console)

Local commands (EXIT, HELP, CLEAR) stop after parsing. In a script they are skipped, and the
first error stops the script.
"""

import logging
from pathlib import Path

from pc_tool import (
    MdtError,
    command_client,
    command_parser,
    command_rules,
    target_model,
    user_console,
)

log = logging.getLogger(__name__)


class DebugSession:
    def __init__(self, target: target_model.Target, specs: dict[str, command_parser.CommandSpec],
                 client: command_client.CommandClient, console: user_console.Console) -> None:
        self._target = target
        self._specs = specs
        self._client = client
        self._console = console

    def repl(self) -> None:
        """Read and run lines until EXIT, end of input or Ctrl-C."""
        self._console.intro()
        while True:
            try:
                line = self._console.read_line()
            except (EOFError, KeyboardInterrupt):
                self._console.info("Exiting...")
                return
            try:
                if not self.run_line(line):
                    return
            except MdtError as exc:
                log.error("%s", exc, extra=user_console.error_extra(exc.code))

    def run_line(self, line: str) -> bool:
        """Run one line; False when it ends the session (EXIT). Raises CommandError or NoReplyError."""
        command = command_parser.parse(line, self._specs, self._target)
        if command is None:
            return True
        if self._specs[command.name].local:
            return self._run_local(command.name)
        log.info("Parsed Command: %s", command)
        command_rules.check(command, self._target)
        self._send(command)
        return True

    def run_script(self, path: str) -> bool:
        """Run a script file; True if every line ran. Blank lines and # comments are skipped."""
        try:
            lines = Path(path).read_text().splitlines()
        except OSError as exc:
            log.error("Cannot open script file: %s", exc, extra=user_console.error_extra(1))
            return False
        log.info("Running script: %s (%d lines)", path, len(lines))
        ok = self._run_script_lines(lines)
        log.info("Script complete.")
        return ok

    def _run_script_lines(self, lines: list[str]) -> bool:
        for number, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            log.info("[%d] %s", number, line)
            try:
                command = command_parser.parse(line, self._specs, self._target)
            except command_parser.CommandError as exc:
                return self._abort(exc, f"parse error at line {number}: {line!r}", 2)
            if self._specs[command.name].local:
                log.warning("Skipping PC-only command at line %d: %s", number, command.name)
                continue
            try:
                command_rules.check(command, self._target)
            except command_parser.CommandError as exc:
                return self._abort(exc, f"validation failed at line {number}: {line!r}", 3)
            try:
                self._send(command)
            except command_client.NoReplyError as exc:
                return self._abort(exc, f"no reply at line {number}: {line!r}", 4)
        return True

    def _abort(self, exc: MdtError, why: str, code: int) -> bool:
        log.error("%s", exc, extra=user_console.error_extra(exc.code))
        log.error("Script aborted: %s", why, extra=user_console.error_extra(code))
        return False

    def _send(self, command) -> None:
        """Send *command* and show every reply, also the ones before a NoReplyError."""
        try:
            replies = self._client.run(command)
        except command_client.NoReplyError as exc:
            for reply in exc.replies:
                self._console.packet(reply)
            raise
        for reply in replies:
            self._console.packet(reply)

    def _run_local(self, name: str) -> bool:
        if name == "EXIT":
            return False
        if name == "HELP":
            self._console.help(self._specs)
        elif name == "CLEAR":
            self._console.clear()
        return True
