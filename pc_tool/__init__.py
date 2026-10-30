"""MCU-MDT PC tool: talks to the MDT firmware library over a serial port."""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())   # the app (cli_main) adds the real handlers


class MdtError(Exception):
    """Base of every error the PC tool raises on purpose; its message is meant for the user."""

    code = 1                            # the error code shown with it: ERROR: <message> (<code>)
