from __future__ import annotations
import logging
import os
from datetime import datetime


class _TerminalHandler(logging.Handler):
    """Forward warning/error records to ``Terminal._emit_from_logger``.

    Installed on the MCU-MDT logger so existing call sites of the form
    ``MDTLogger.error("Unknown command: X", code=3)`` automatically
    surface to the user — without every parser/validator call site
    needing to know about Terminal.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        # Lazy import to break a circular dependency
        # (terminal.py imports MDTLogger at runtime for its log mirror).
        try:
            from pc_tool.common.terminal import Terminal
        except Exception:
            return

        try:
            msg = record.getMessage()
            code = getattr(record, "code", "")
            if code:
                msg = f"{msg} {code}"
            Terminal._emit_from_logger(record.levelno, msg)
        except Exception:
            # Logging must never raise.
            self.handleError(record)


class _MDTLogger:
    """Named ``logging.Logger`` wrapper, file-only by default.

    Instantiated once at module level as ``MDTLogger``.  Call sites do
    ``MDTLogger.info(...)``, ``MDTLogger.error(...)``, etc.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("MCU-MDT")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # Wipe any handlers a prior import/test cycle may have left behind
        # so re-importing this module is idempotent.
        for h in list(self._logger.handlers):
            self._logger.removeHandler(h)

        self._formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s]%(code)s: %(message)s",
            datefmt="%H:%M:%S",
        )

        # Always-on null handler keeps Python's logging machinery happy
        # before enable_file_logging() is called.
        self._logger.addHandler(logging.NullHandler())

        # Terminal-routing handler: WARNING+ records flow to Terminal.
        term_handler = _TerminalHandler()
        term_handler.setFormatter(self._formatter)
        self._logger.addHandler(term_handler)

        self._log_file: str | None = None

    # Setup
    def enable_file_logging(self, log_dir: str = "logs", mcu: str = "unknown") -> str:
        """Attach a timestamped file handler, creating ``log_dir`` if needed.

        Call once from ``main()`` after build info is available.
        Returns the path of the log file opened.
        """
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(log_dir, f"mdt_{mcu}_{timestamp}.log")

        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        handler.setFormatter(self._formatter)
        self._logger.addHandler(handler)
        self._log_file = path
        return path

    # Back-compat shims.  The old API silenced/restored the stream
    # handler that used to live on the logger.  That handler is gone,
    # but main.py still calls these in script mode to mute output —
    # the right modern target for that is the Terminal's quiet flag.
    def suppress_console(self) -> None:
        """Silence Terminal output (script mode).  No-op on the logger."""
        try:
            from pc_tool.common.terminal import Terminal
            Terminal.set_quiet(True)
        except Exception:
            pass

    def restore_console(self) -> None:
        """Restore Terminal output."""
        try:
            from pc_tool.common.terminal import Terminal
            Terminal.set_quiet(False)
        except Exception:
            pass

    # File only session marker
    def _emit_to_file(self, msg: str) -> None:
        for h in self._logger.handlers:
            if isinstance(h, logging.FileHandler):
                record = self._logger.makeRecord(
                    self._logger.name, logging.INFO, "", 0, msg, [], None
                )
                record.__dict__["code"] = ""
                h.emit(record)

    def session_start(self, build_info: dict) -> None:
        """Write session header with build metadata to the log file."""
        sep = "=" * 60
        for line in [
            sep,
            "MCU-MDT SESSION START",
            f"  MCU      : {build_info.get('mcu',      'unknown')}",
            f"  Platform : {build_info.get('platform', 'unknown')}",
            f"  Port     : {build_info.get('port',     'unknown')}",
            f"  Baudrate : {build_info.get('baudrate',   19200)}",
            f"  Log file : {self._log_file or 'none'}",
            sep,
        ]:
            self._emit_to_file(line)

    def session_end(self) -> None:
        """Write session footer to the log file."""
        sep = "=" * 60
        for line in [sep, "MCU-MDT SESSION END", sep]:
            self._emit_to_file(line)

    # API
    def _log(self, level: int, msg: str, code: int | None) -> None:
        extra = {"code": f"({code})" if code is not None else ""}
        self._logger.log(level, msg, extra=extra)

    def info(self,    msg: str, code: int | None = None) -> None: self._log(logging.INFO,    msg, code)
    def warning(self, msg: str, code: int | None = None) -> None: self._log(logging.WARNING, msg, code)
    def error(self,   msg: str, code: int | None = None) -> None: self._log(logging.ERROR,   msg, code)
    def debug(self,   msg: str, code: int | None = None) -> None: self._log(logging.DEBUG,   msg, code)


MDTLogger = _MDTLogger()