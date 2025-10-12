from loader import load_configs
from parser import parse_line

if __name__ == "__main__":
    commands = load_configs('configs/commands.yaml')['commands']
    command_history = []

    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue

            command = parse_line(line, commands)
            command_history.append(line)

            if not command:
                print("Invalid command or parsing error.")
                continue

            if command.name == "EXIT":
                print("Exiting...")
                break

            print(f"Parsed Command: {command}")
        except EOFError as end_of_file:
            print("\nExiting...")
            break
        except KeyboardInterrupt as keyboard_interrupt:
            print("\n Exiting with keyboard interrupt...")
            break