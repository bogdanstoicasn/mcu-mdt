from loader import load_configs
from parser import parse_line
from commander import execute_command

if __name__ == "__main__":
    yaml_command_data = load_configs('configs/commands.yaml')
    commands = yaml_command_data['commands']
    mem_types = yaml_command_data['mem_types']
    command_history = []

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
                # TODO: implement help
                pass

            print(f"Parsed Command: {command}")

            execute_command(command)
        except EOFError as end_of_file:
            print("\nExiting...")
            break
        except KeyboardInterrupt as keyboard_interrupt:
            print("\n Exiting with keyboard interrupt...")
            break