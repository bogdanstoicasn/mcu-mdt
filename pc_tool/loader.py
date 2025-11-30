import yaml
import os
from logger import log, LogLevel

def load_configs(file_path: str) -> dict:
    """Load configurations from a YAML file."""
    with open(file_path, 'r') as f:
        try:
            configs = yaml.safe_load(f)
            return configs
        except yaml.YAMLError as e:
            log(log_level=LogLevel.ERROR, module="loader", msg="Failed to load YAML file", code=str(e))
            return {}

def load_platforms(file_path: str) -> dict:
    """Load platform yaml data recursive from a folder."""
    platforms = {}
    for root, _, files in os.walk(file_path):
        for file in files:
            if file.endswith('.yaml') or file.endswith('.yml'):
                full_path = os.path.join(root, file)
                platform = load_configs(full_path)
                platform_name = platform['arch'].get('name')
                if platform_name:
                    platforms[platform_name] = platform
    return platforms
