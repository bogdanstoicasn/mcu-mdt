import logging
import inspect
import os
from datetime import datetime
from enum import Enum
from typing import Optional

class LogLevel(Enum):
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    DEBUG = logging.DEBUG

class MDTLogger:
    _instance = None

    def __new__(cls, level: LogLevel = LogLevel.DEBUG):
        if cls._instance is None:
            cls._instance = super(MDTLogger, cls).__new__(cls)

            cls._instance._logger = logging.getLogger("MCU-MDT")
            cls._instance._logger.setLevel(level.value)
            cls._instance._logger.propagate = False

            cls._instance._formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s]%(code)s: %(message)s",
                datefmt="%H:%M:%S"
            )

            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(cls._instance._formatter)
            cls._instance._logger.addHandler(stream_handler)

            cls._instance._log_file = None

        return cls._instance

    def enable_file_logging(self, log_dir: str = "logs", mcu: str = "unknown") -> str:
        """
        Attach a timestamped file handler. Creates log_dir if needed.
        Returns the path of the log file opened.
        Call once from main() after build info is available.
        """
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(log_dir, f"mdt_{mcu}_{timestamp}.log")

        file_handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        file_handler.setFormatter(self._formatter)
        self._logger.addHandler(file_handler)
        self._log_file = path
        return path

    def suppress_console(self) -> None:
        """Silence the stream handler: output goes to file only."""
        for handler in self._logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.CRITICAL + 1)

    def restore_console(self) -> None:
        """Restore the stream handler to its normal level."""
        for handler in self._logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.DEBUG)

    def _log_file_only(self, msg: str) -> None:
        """Write a line to the log file only, bypassing the console handler."""
        for handler in self._logger.handlers:
            if isinstance(handler, logging.FileHandler):
                record = self._logger.makeRecord(
                    self._logger.name, logging.INFO, "", 0, msg, [], None
                )
                record.__dict__["code"] = ""
                handler.emit(record)

    def session_start(self, build_info: dict) -> None:
        """Log session header with build metadata: file only."""
        sep = "=" * 60
        for line in [
            sep,
            "MCU-MDT SESSION START",
            f"  MCU      : {build_info.get('mcu', 'unknown')}",
            f"  Platform : {build_info.get('platform', 'unknown')}",
            f"  Port     : {build_info.get('port', 'unknown')}",
            f"  Baudrate : {build_info.get('baudrate', 19200)}",
            f"  Log file : {self._log_file or 'none'}",
            sep,
        ]:
            self._log_file_only(line)

    def session_end(self) -> None:
        """Log session footer: file only."""
        sep = "=" * 60
        for line in [sep, "MCU-MDT SESSION END", sep]:
            self._log_file_only(line)

    def log(self, level: LogLevel, msg: str, code: Optional[int] = None):
        frame = inspect.currentframe()
        caller_frame = frame.f_back.f_back
        module_name = caller_frame.f_globals.get("__name__", "unknown")
        extra = {"src": module_name, "code": f"({code})" if code is not None else ""}
        self._logger.log(level.value, msg, extra=extra)

    def info(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.INFO, msg, code)

    def warning(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.WARNING, msg, code)

    def error(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.ERROR, msg, code)

    def debug(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.DEBUG, msg, code)

    def set_level(self, level: LogLevel):
        self._logger.setLevel(level.value)


MDTLogger = MDTLogger()