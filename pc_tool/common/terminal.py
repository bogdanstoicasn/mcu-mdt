"""Terminal output layer for MCU-MDT.

Plain-text presentation layer.  No colour, no TTY probing, no
per-field formatting helpers — just direct writes for speed.

    MDTLogger  -> file-only audit trail
    Terminal   -> what the user sees in their shell

Every Terminal call still mirrors a single line to attached file
handlers (via a direct stream write, bypassing the logging Formatter
and emit chain) so the audit log stays complete without the per-call
``makeRecord`` cost.
"""

from __future__ import annotations

import os
import sys
import time
import logging


# Fixed box width for the packet view.  Avoids a syscall
# (``shutil.get_terminal_size``) on every print.
_BOX_W = 64


class _TerminalPrinter:
    """Module-level singleton — see ``Terminal`` at the bottom of the file."""

    def __init__(self) -> None:
        self._quiet = False

    # Quiet mode
    def set_quiet(self, quiet: bool) -> bool:
        """Toggle output silencing.  Returns the previous state."""
        prev = self._quiet
        self._quiet = bool(quiet)
        return prev

    def is_quiet(self) -> bool:
        return self._quiet

    # Internal
    def _write(self, line: str) -> None:
        """Single stdout write, no flush.  On a TTY, the newline at the
        end of a line triggers the flush itself; on a pipe, block
        buffering is desirable.  Callers that need an immediate flush
        (e.g. ``event``, which doesn't end with a newline) flush explicitly.
        """
        if self._quiet:
            return
        sys.stdout.write(line)

    def _log_mirror(self, level: int, msg: str) -> None:
        """Append a pre-formatted line directly to attached file handlers.

        Bypasses ``logger.makeRecord`` / formatter / ``Handler.emit``,
        which is the chunk of work we don't need: the line format is
        fixed and matches what the logger's own formatter would produce
        for an empty ``code`` field.  Acquires each handler's lock so
        we don't interleave with other threads.
        """
        try:
            from pc_tool.common.logger import MDTLogger
            logger = MDTLogger._logger
            if not logger.isEnabledFor(level):
                return
            line = (
                f"[{time.strftime('%H:%M:%S')}] "
                f"[{logging.getLevelName(level)}]: {msg}\n"
            )
            for h in logger.handlers:
                if isinstance(h, logging.FileHandler):
                    stream = getattr(h, "stream", None)
                    if stream is None:
                        continue
                    with h.lock:
                        stream.write(line)
                        stream.flush()  # keep the audit log durable
        except Exception:
            pass  # never let logging failure break the UI

    # Level-style messages
    def error(self, msg: str) -> None:
        self._write(f"ERROR: {msg}\n")
        self._log_mirror(logging.ERROR, msg)

    def warning(self, msg: str) -> None:
        self._write(f"WARN:  {msg}\n")
        self._log_mirror(logging.WARNING, msg)

    def success(self, msg: str) -> None:
        self._write(f"OK:    {msg}\n")
        self._log_mirror(logging.INFO, msg)

    def info(self, msg: str) -> None:
        self._write(f"{msg}\n")
        self._log_mirror(logging.INFO, msg)

    # Routed-from-logger entry point
    # Called by ``_TerminalHandler`` in logger.py.  Prints without
    # re-logging (the original record was already logged to file).
    def _emit_from_logger(self, level: int, msg: str) -> None:
        if self._quiet:
            return
        if level >= logging.ERROR:
            self._write(f"ERROR: {msg}\n")
        elif level >= logging.WARNING:
            self._write(f"WARN:  {msg}\n")
        else:
            self._write(f"{msg}\n")

    # CLI widgets
    def clear(self) -> None:
        if self._quiet:
            return
        os.system('cls' if os.name == 'nt' else 'clear')

    def intro(self, text: str) -> None:
        self._write(text + "\n")

    def help_table(self, lines) -> None:
        self._write("\n" + "\n".join(lines) + "\n\n")

    def event(self, msg: str) -> None:
        """Async event line.  Clears the current input line and re-prints
        the prompt so the user's half-typed command isn't garbled.
        Flushes explicitly because the trailing ``> `` has no newline.
        """
        if not self._quiet:
            sys.stdout.write(f"\r\033[K{msg}\n> ")
            sys.stdout.flush()
        self._log_mirror(logging.INFO, f"[event] {msg}")

    # Packet pretty-print
    def packet(self, cmd_packet, raw: bytes | None = None) -> None:
        """Render a CommandPacket as a labelled box.

        The whole output is built once and written in a single
        ``sys.stdout.write`` call to minimise syscalls.
        """
        # Imported lazily to keep this module dependency-light
        from pc_tool.common.enums import MDTFlags, CommandId

        # Decode the command id
        try:
            cmd_field = f"{CommandId(cmd_packet.cmd_id).name} (0x{cmd_packet.cmd_id:02X})"
        except ValueError:
            cmd_field = f"<unknown> (0x{cmd_packet.cmd_id:02X})"

        # Decode flags
        flag_names = [f.name for f in MDTFlags if cmd_packet.flags & f]
        flags_field = (
            f"0x{cmd_packet.flags:02X}  "
            + (" | ".join(flag_names) if flag_names else "<none>")
        )

        # Status badge: pure ASCII, no colour
        is_ack   = bool(cmd_packet.flags & MDTFlags.ACK_NACK)
        is_err   = bool(cmd_packet.flags & MDTFlags.STATUS_ERROR)
        is_event = bool(cmd_packet.flags & MDTFlags.EVENT_PACKET)

        if is_event:
            badge = "[EVENT]"
        elif is_ack and is_err:
            badge = "[NACK]"
        elif is_ack:
            badge = "[ACK]"
        else:
            badge = "[COMMAND]"

        # Spaced hex:  DE AD BE EF
        data_hex = (
            " ".join(f"{b:02X}" for b in cmd_packet.data)
            if cmd_packet.data is not None else "<none>"
        )
        mem_field = (
            f"0x{cmd_packet.mem_id:02X} ({cmd_packet.mem_id})"
            if cmd_packet.mem_id is not None else "<not present>"
        )
        crc_field = (
            f"0x{cmd_packet.crc:04X}"
            if cmd_packet.crc is not None else "<none>"
        )
        length_field = str(cmd_packet.length if cmd_packet.length is not None else 0)

        parts = [
            "┌─ Received Packet " + "─" * max(1, _BOX_W - 19),
            f"│  Status   : {badge}",
            f"│  Command  : {cmd_field}",
            f"│  Flags    : {flags_field}",
            f"│  Sequence : {cmd_packet.seq}",
            f"│  Mem ID   : {mem_field}",
            f"│  Address  : 0x{cmd_packet.address:08X}",
            f"│  Length   : {length_field}",
            f"│  Data     : {data_hex}",
            f"│  CRC      : {crc_field}",
        ]
        if raw is not None:
            parts.append(f"│  raw      : {raw.hex()}")
        parts.append("└" + "─" * (_BOX_W - 1))
        parts.append("")  # trailing newline after the box

        self._write("\n".join(parts))
        self._log_mirror(logging.INFO, f"Received packet: {cmd_packet}")


# Module-level singleton.  Mirrors the MDTLogger pattern.
Terminal = _TerminalPrinter()