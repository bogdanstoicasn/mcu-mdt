"""Run the PC tool from a checkout without installing it: python3 mcu_mdt.py build/<part>/build_info.yaml"""

import sys

from pc_tool import cli_main

if __name__ == "__main__":
    sys.exit(cli_main.main())
