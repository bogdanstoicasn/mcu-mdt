import yaml
import os
import xml.etree.ElementTree as ET
from logger import log, LogLevel
from common.enums import MCUPlatforms

class ConfigLoader:
    def __init__(
        self,
        build_info_path: str,
        commands_path: str = "configs/commands.yaml",
        platforms_path: str = "configs/platforms",
    ):
        self.yaml_build_data = load_configs(build_info_path)
        self.yaml_command_data = load_configs(commands_path)
        self.yaml_platform_data = load_platforms(platforms_path)

        mcu = self.yaml_build_data.get('mcu')
        platform = self.yaml_build_data.get('platform')


        self.mcu_metadata = load_mcu_metadata(mcu, platform)


def load_configs(file_path: str) -> dict:
    """Load configurations from a YAML file."""
    with open(file_path, 'r') as f:
        try:
            configs = yaml.safe_load(f)
            return configs
        except yaml.YAMLError as e:
            log(log_level=LogLevel.ERROR, module="loader", msg="Failed to load YAML file", code=str(e))
            return {}

def load_platforms(folder_path: str) -> dict:
    """Load platform YAML files recursively from a folder."""
    platforms = {}

    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.endswith(('.yaml', '.yml')):
                continue

            full_path = os.path.join(root, file)
            platform = load_configs(full_path)

            # Prefer explicit platform_name
            platform_name = platform.get("platform_name")

            if not platform_name:
                raise ValueError(
                    f"Missing 'platform_name' in platform file: {full_path}"
                )

            platforms[platform_name] = platform

    return platforms

def load_atdf_for_mcu(mcu_name: str, atdf_root: str) -> dict:
    """
    Locate and parse the ATDF file for a given MCU.

    Args:
        mcu_name (str): MCU name (e.g. 'atmega328p')
        atdf_root (str): Path to extracted ATDF directory

    Returns:
        dict: Parsed ATDF data (registers, memories, peripherals, etc.)

    Raises:
        FileNotFoundError: If ATDF file cannot be found
        ValueError: If ATDF is invalid or MCU mismatch
    """

    mcu_name = mcu_name.lower()
    atdf_file = None

    # 1. Locate ATDF file
    for root, _, files in os.walk(atdf_root):
        for file in files:
            if file.lower().endswith(".atdf"):
                file_stem = os.path.splitext(file)[0].lower()
                if file_stem == mcu_name:
                    atdf_file = os.path.join(root, file)
                    break
        if atdf_file:
            break

    if not atdf_file:
        raise FileNotFoundError(
            f"ATDF file for MCU '{mcu_name}' not found in {atdf_root}"
        )

    # 2. Parse XML
    try:
        tree = ET.parse(atdf_file)
        root = tree.getroot()
    except ET.ParseError as e:
        raise ValueError(f"Invalid ATDF XML: {e}")

    # 3. Basic validation
    device = root.find("devices/device")
    if device is None:
        raise ValueError("ATDF missing <device> entry")

    device_name = device.get("name", "").lower()
    if device_name != mcu_name:
        raise ValueError(
            f"ATDF device mismatch: expected {mcu_name}, found {device_name}"
        )

    # 4. Extract useful info
    result = {
        "device": device_name,
        "architecture": device.get("architecture"),
        "family": device.get("family"),
        "peripherals": {},
        "modules": {},
        "memories": {},
        "interrupts": {},
    }

    # 5. Parse memories
    for mem in root.findall(".//memory-segment"):
        name = mem.get("name")
        if name:
            result["memories"][name] = {
                "start": int(mem.get("start", "0"), 0),
                "size": int(mem.get("size", "0"), 0),
                "type": mem.get("type"),
                "pagesize": mem.get("pagesize"),
            }

    # 6. Parse modules (peripherals with their register groups)
    for module in root.findall(".//modules/module"):
        mod_name = module.get("name")
        if not mod_name:
            continue
            
        result["modules"][mod_name] = {
            "caption": module.get("caption"),
            "instances": [],
            "register_groups": {},
        }

        # Parse instances
        for inst in module.findall(".//instance"):
            inst_data = {
                "name": inst.get("name"),
            }
            # Get register group reference
            for reg_group in inst.findall(".//register-group"):
                inst_data["register_group"] = reg_group.get("name-in-module")
                inst_data["offset"] = reg_group.get("offset")
                inst_data["address_space"] = reg_group.get("address-space")
            
            result["modules"][mod_name]["instances"].append(inst_data)

        # Parse register groups for this module
        for reg_group in module.findall(".//register-group"):
            rg_name = reg_group.get("name")
            if not rg_name:
                continue
                
            result["modules"][mod_name]["register_groups"][rg_name] = {
                "name_in_module": reg_group.get("name-in-module"),
                "caption": reg_group.get("caption"),
                "offset": reg_group.get("offset"),
                "registers": {},
            }

            # Parse individual registers
            for register in reg_group.findall(".//register"):
                reg_name = register.get("name")
                if not reg_name:
                    continue
                    
                reg_data = {
                    "caption": register.get("caption"),
                    "offset": register.get("offset"),
                    "size": register.get("size"),
                    "mask": register.get("mask"),
                    "rw": register.get("rw"),
                    "bitfields": {},
                }

                # Parse bitfields
                for bitfield in register.findall(".//bitfield"):
                    bf_name = bitfield.get("name")
                    if bf_name:
                        reg_data["bitfields"][bf_name] = {
                            "caption": bitfield.get("caption"),
                            "mask": bitfield.get("mask"),
                            "values": {},
                        }
                        
                        # Parse bitfield values
                        for value in bitfield.findall(".//value"):
                            val_name = value.get("name")
                            if val_name:
                                reg_data["bitfields"][bf_name]["values"][val_name] = {
                                    "caption": value.get("caption"),
                                    "value": value.get("value"),
                                }

                result["modules"][mod_name]["register_groups"][rg_name]["registers"][reg_name] = reg_data

    # 7. Parse interrupts
    for interrupt in root.findall(".//interrupts/interrupt"):
        int_name = interrupt.get("name")
        if int_name:
            result["interrupts"][int_name] = {
                "index": interrupt.get("index"),
                "caption": interrupt.get("caption"),
                "module_instance": interrupt.get("module-instance"),
            }

    # 8. Parse peripheral instances (alternative structure)
    for periph in root.findall(".//peripherals/module"):
        pname = periph.get("name")
        if pname and pname not in result["peripherals"]:
            result["peripherals"][pname] = {
                "caption": periph.get("caption"),
                "instances": [],
            }

            for inst in periph.findall(".//instance"):
                result["peripherals"][pname]["instances"].append({
                    "name": inst.get("name"),
                })

    return result

def load_svd_for_mcu(mcu_name: str, svd_root: str) -> dict:
    """
    Parse an ARM Cortex-M SVD file and produce ATDF-compatible metadata.

    Args:
        mcu_name (str): MCU name, e.g., 'STM32F103C8'
        svd_root (str): Folder containing the SVD file

    Returns:
        dict: metadata with keys: modules, memories, peripherals, interrupts
    """
    mcu_name_lower = mcu_name.lower()
    svd_file = None

    # Locate SVD
    for root, _, files in os.walk(svd_root):
        for file in files:
            if file.lower().endswith(".svd"):
                file_stem = os.path.splitext(file)[0].lower()
                if file_stem == mcu_name_lower:
                    svd_file = os.path.join(root, file)
                    break
        if svd_file:
            break

    if not svd_file:
        raise FileNotFoundError(f"SVD file for MCU '{mcu_name}' not found in {svd_root}")

    # Parse XML
    tree = ET.parse(svd_file)
    root = tree.getroot()

    result = {
        "device": mcu_name_lower,
        "architecture": root.findtext("cpu/name"),
        "family": root.findtext("cpu/description"),
        "peripherals": {},
        "modules": {},
        "memories": {},
        "interrupts": {},
    }

    # 1. Parse memories (Flash, SRAM)
    memory_map = root.findall(".//memory")
    for mem in memory_map:
        name = mem.get("name")
        start = int(mem.get("startAddress") or mem.get("baseAddress") or 0, 0)
        size = int(mem.get("size") or 0, 0)
        mem_type = mem.get("access")  # optional, map to 'flash' or 'ram'
        mem_type_str = "flash" if "flash" in (name or "").lower() else "ram"
        result["memories"][name] = {
            "start": start,
            "size": size,
            "type": mem_type_str,
            "pagesize": mem.get("pageSize"),
        }

    # 2. Parse peripherals and registers
    for peripheral in root.findall(".//peripheral"):
        periph_name = peripheral.findtext("name")
        if not periph_name:
            continue

        # Module
        result["modules"][periph_name] = {
            "caption": peripheral.findtext("description"),
            "instances": [],
            "register_groups": {},
        }

        # Base address
        base_addr = int(peripheral.findtext("baseAddress") or 0, 0)

        # Registers
        rg_name = "REG_GROUP"
        result["modules"][periph_name]["register_groups"][rg_name] = {
            "name_in_module": rg_name,
            "caption": rg_name,
            "offset": 0,
            "registers": {},
        }

        for reg in peripheral.findall("registers/register"):
            reg_name = reg.findtext("name")
            if not reg_name:
                continue
            reg_offset = int(reg.findtext("addressOffset") or 0, 0)
            reg_size = int(reg.findtext("size") or 32, 0)  # default 32-bit
            reg_rw = reg.findtext("access") or "read-write"

            # Bitfields
            bitfields = {}
            for bf in reg.findall("fields/field"):
                bf_name = bf.findtext("name")
                if not bf_name:
                    continue
                bf_mask = bf.findtext("bitRange") or bf.findtext("bitOffset")
                bf_values = {}
                for val in bf.findall("enumeratedValues/enumeratedValue"):
                    val_name = val.findtext("name")
                    if val_name:
                        bf_values[val_name] = {
                            "caption": val.findtext("description"),
                            "value": val.findtext("value"),
                        }
                bitfields[bf_name] = {"caption": bf.findtext("description"), "mask": bf_mask, "values": bf_values}

            result["modules"][periph_name]["register_groups"][rg_name]["registers"][reg_name] = {
                "caption": reg.findtext("description"),
                "offset": reg_offset,
                "size": reg_size,
                "rw": reg_rw,
                "bitfields": bitfields,
            }

    return result

def load_mcu_metadata(mcu_name: str, mcu_platform: str) -> dict:

    platform = mcu_platform.lower()

    if platform == MCUPlatforms.AVR:
        return load_atdf_for_mcu(mcu_name, atdf_root="mcu_db")
    elif platform == MCUPlatforms.PIC:
        # Placeholder for PIC metadata loading logic
        raise NotImplementedError("PIC platform support not implemented yet")
    elif platform == MCUPlatforms.STM:
        # Placeholder for STM metadata loading logic
        raise NotImplementedError("STM platform support not implemented yet")
    else:
        raise ValueError(f"Unsupported MCU platform: {platform}")

