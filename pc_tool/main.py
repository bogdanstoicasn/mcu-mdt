from loader import load_configs, load_platforms, load_atdf_for_mcu
from parser import parse_line, parse_args
from commander import execute_command, help_command, intro_text, ping_command
from validator import validate_commands

if __name__ == "__main__":
    args = parse_args()

    build_info_path = args.build_info

    yaml_build_data = load_configs(build_info_path)

    yaml_command_data = load_configs('configs/commands.yaml')

    yaml_platform_data = load_platforms('configs/platforms')

    commands = yaml_command_data['commands']

    mem_types = yaml_command_data['mem_types']

    atdf_data = load_atdf_for_mcu(
        yaml_build_data['mcu'],
        atdf_root="atdf"
    )

    command_history = []

    print(intro_text())

    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue

            command = parse_line(line, commands, mem_types)
            command_history.append(line)

            if not command:
                print("Invalid command or parsing error.")
                continue

            # Handle the CLI commands(EXIT, HELP) directly here
            if command.name == "EXIT":
                print("Exiting...")
                break
            elif command.name == "HELP":
                help_command()
                continue
            elif command.name == "PING":
                ping_command(command, yaml_build_data)
                continue


            print(f"Parsed Command: {command}")

            if not validate_commands(command, atdf_data):
                print("Command validation failed.")
                continue

            execute_command(command)
        except EOFError as end_of_file:
            print("\nExiting...")
            break
        except KeyboardInterrupt as keyboard_interrupt:
            print("\n Exiting with keyboard interrupt...")
            break