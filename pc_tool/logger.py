import sys
from enum import Enum

class LogLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"

def log(level, module, msg, code = None):
    code_str = f"({code})" if code else ""
    print(f"[{level}] [{module}]{code_str}: {msg}", file=sys.stderr)