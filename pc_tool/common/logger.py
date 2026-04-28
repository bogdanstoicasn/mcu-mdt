import logging
import os
from datetime import datetime


class _MDTLogger:
    """Thin wrapper around a named ``logging.Logger`` with file logging support.

    Instantiated once at module level as ``MDTLogger``. All call sites use
    ``MDTLogger.info()``, ``MDTLogger.error()``, etc.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("MCU-MDT")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        self._formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s]%(code)s: %(message)s",
            datefmt="%H:%M:%S",
        )

        handler = logging.StreamHandler()
        handler.setFormatter(self._formatter)
        self._logger.addHandler(handler)

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

    def suppress_console(self) -> None:
        """Silence the stream handler so output goes to file only."""
        for h in self._logger.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(logging.CRITICAL + 1)

    def restore_console(self) -> None:
        """Restore the stream handler to DEBUG level."""
        for h in self._logger.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(logging.DEBUG)

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