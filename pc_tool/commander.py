"""Console helpers: the intro, HELP, CLEAR and the clean shutdown."""

import shutil

from pc_tool.common.terminal import Terminal


def intro_text() -> str:
    """Generate centered intro text based on terminal width."""
    width = shutil.get_terminal_size().columns
    lines = [
        "MCU-MDT - Microcontroller Memory Debug Tool",
        "---------------------------------------",
        "Type 'HELP' to see available commands.",
    ]
    return "\n" + "\n".join(line.center(width) for line in lines) + "\n"


def help_command(specs: dict) -> None:
    """Display available commands and their descriptions, formatted based on terminal width."""
    width = shutil.get_terminal_size().columns
    col1  = 32

    lines = ["─" * min(width, 72), "  MCU-MDT — Available Commands", "─" * min(width, 72)]
    for spec in specs.values():
        usage = f"  {spec.usage}"
        if len(usage) < col1:
            lines.append(f"{usage.ljust(col1)}{spec.description}")
        else:
            lines.append(usage)
            lines.append(f"{''.ljust(col1)}{spec.description}")
    lines.append("─" * min(width, 72))
    Terminal.help_table(lines)


def clear_command() -> None:
    """Clear the terminal screen."""
    Terminal.clear()


def exit_command(link, pump) -> None:
    """Stop the event pump, then close the link."""
    pump.stop()
    link.close()
    Terminal.success("Debugger closed.")
