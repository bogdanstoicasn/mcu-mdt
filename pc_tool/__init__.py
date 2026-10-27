"""MCU-MDT PC tool: talks to the MDT firmware library over a serial port."""


class MdtError(Exception):
    """Base of every error the PC tool raises on purpose; its message is meant for the user."""
