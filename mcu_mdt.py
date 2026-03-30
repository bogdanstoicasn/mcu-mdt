import os
import sys

# Project root on sys path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from pc_tool.main import main
from pc_tool.parser import parse_args


def cli_main():
    args = parse_args()
    main(args)


if __name__ == "__main__":
    cli_main()