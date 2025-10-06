import yaml
from logger import log, LogLevel

def load_configs(file_path: str) -> dict:
    with open(file_path, 'r') as f:
        try:
            configs = yaml.safe_load(f)
            return configs
        except yaml.YAMLError as e:
            log(log_level=LogLevel.ERROR, module="loader", msg="Failed to load YAML file", code=str(e))
            return {}
