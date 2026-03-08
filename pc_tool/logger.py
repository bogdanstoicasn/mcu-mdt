import logging
import inspect
from enum import Enum
from typing import Optional

class LogLevel(Enum):
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    DEBUG = logging.DEBUG

class MDTLogger:
    _instance = None

    def __new__(cls, log_file: Optional[str] = None, level: LogLevel = LogLevel.DEBUG):
        if cls._instance is None:
            cls._instance = super(MDTLogger, cls).__new__(cls)

            # Create internal logger
            cls._instance._logger = logging.getLogger("MCU-MDT")
            cls._instance._logger.setLevel(level.value)
            cls._instance._logger.propagate = False  # Avoid double logging

            # Stream handler for stderr
            stream_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s]%(code)s: %(message)s",
                datefmt="%H:%M:%S"
            )
            stream_handler.setFormatter(formatter)
            cls._instance._logger.addHandler(stream_handler)

            # Optional file handler
            if log_file:
                file_handler = logging.FileHandler(log_file, mode="a")
                file_handler.setFormatter(formatter)
                cls._instance._logger.addHandler(file_handler)

        return cls._instance

    def log(self, level: LogLevel, msg: str, code: Optional[int] = None):
        # Automatic module detection
        frame = inspect.currentframe()
        caller_frame = frame.f_back.f_back  # caller of log()
        module_name = caller_frame.f_globals.get("__name__", "unknown")

        extra = {"src": module_name, "code": f"({code})" if code is not None else ""}
        self._logger.log(level.value, msg, extra=extra)

    # Convenience methods
    def info(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.INFO, msg, code)

    def warning(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.WARNING, msg, code)

    def error(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.ERROR, msg, code)

    def debug(self, msg: str, code: Optional[int] = None):
        self.log(LogLevel.DEBUG, msg, code)


# Singleton instance
MDTLogger = MDTLogger()