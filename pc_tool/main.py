from loader import load_configs, load_platforms, load_atdf_for_mcu
from parser import parse_line, parse_args
from commander import execute_command, help_command, intro_text, clear_command, ping_command, serial_link_command
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

    # Start the connection to the MCU
    serial_link = serial_link_command(
        port=yaml_build_data['port'],
        baudrate=yaml_build_data.get('baudrate', 19200),
        ping_command_id=commands['PING']['id']
    )
    try:
        serial_link.open()
    except Exception as e:
        print(f"Failed to open serial link: {e}")
        exit(1)

    print(intro_text())

    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue

            command = parse_line(line, commands, mem_types)

            if not command:
                print("Invalid command or parsing error.")
                continue

            # Handle the CLI commands(EXIT, HELP) directly here
            if command.name == "EXIT":
                print("Exiting...")
                serial_link.close()
                break
            elif command.name == "HELP":
                help_command()
                continue
            elif command.name == "CLEAR":
                clear_command()
                continue
            elif command.name == "PING":
                ping_command(command, yaml_build_data, serial_link)
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