import argparse
import atexit
from pathlib import Path

from pc_tool.common.terminal import Terminal
from pc_tool.wire_protocol import decode

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None


class CLIHistory:
    def __init__(self, history_filename=".mdt_history", max_length=1000,
                 completions=None):
        self.max_length = max_length

        # Project root = mcu_mdt/
        project_root = Path(__file__).resolve().parents[1]

        self.history_file = project_root / history_filename

        # Command names for TAB completion (case-insensitive match, emitted
        # uppercase to match the parser). Empty list = completion disabled.
        self._completions = sorted({c.upper() for c in (completions or [])})

        if readline:
            readline.set_history_length(self.max_length)

            if self.history_file.exists():
                try:
                    readline.read_history_file(str(self.history_file))
                except Exception:
                    pass

            if self._completions:
                try:
                    readline.set_completer(self._complete)
                    # Treat only whitespace as a word break so the whole token
                    # (e.g. "READ_") is matched against command names.
                    readline.set_completer_delims(" \t\n")
                    # libreadline uses "tab: complete"; libedit (macOS) differs.
                    if "libedit" in getattr(readline, "__doc__", "") or "":
                        readline.parse_and_bind("bind ^I rl_complete")
                    else:
                        readline.parse_and_bind("tab: complete")
                except Exception:
                    pass

            atexit.register(self._save_history)

    def _complete(self, text, state):
        """readline completer: complete the first word against command names."""
        # Only complete the command (first token); leave argument typing alone.
        buffer = readline.get_line_buffer()
        if buffer[:len(buffer) - len(text)].strip():
            return None  # past the first word, no command completion
        matches = [c for c in self._completions if c.startswith(text.upper())]
        return matches[state] if state < len(matches) else None

    def input(self, prompt="> "):
        return input(prompt)

    def _save_history(self):
        if readline:
            try:
                readline.write_history_file(str(self.history_file))
            except Exception:
                pass

def parse_args():
    """Parse CLI arguments using argparse."""
    parser = argparse.ArgumentParser(description="MCU MDT Debugger CLI")
    parser.add_argument(
        "build_info",
        type=str,
        help="Path to build_info.yaml file",
    )
    parser.add_argument(
        "--elf",
        type=str,
        default=None,
        help="The firmware you flashed (default: the elf named in build_info.yaml, e.g. your "
             "project's mcu_mdt_user.elf instead of the example)",
    )
    parser.add_argument(
        "--script",
        type=str,
        required=False,
        default=None,
        help="Path to a script file with commands to execute (exits after completion)",
    )
    return parser.parse_args()



def parse_packet(packet: bytes) -> None:
    """Print the contents of a received packet in human-readable form."""
    cmd = decode(packet)
    Terminal.packet(cmd, raw=packet)
