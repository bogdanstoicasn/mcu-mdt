from loader import load_configs

if __name__ == "__main__":
    commands = load_configs('configs/commands.yaml')['commands']
    
    print(commands)