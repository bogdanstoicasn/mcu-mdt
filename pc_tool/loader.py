import yaml
import os
import xml.etree.ElementTree as ET
from common.logger import MDTLogger
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
            MDTLogger.error("Failed to load YAML file", code=str(e))
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
    Locate and parse the SVD file for a given MCU.
    Args:
        mcu_name (str): MCU name (e.g. 'stm32f103c8')
        svd_root (str): Path to SVD files directory
    Returns:
        dict: Parsed SVD data (registers, memories, peripherals, etc.)
    Raises:
        FileNotFoundError: If SVD file cannot be found
        ValueError: If SVD is invalid or MCU mismatch
    """

    mcu_name_lower = mcu_name.lower()
    svd_file = None

    # Try exact match
    for root_dir, _, files in os.walk(svd_root):
        for file in files:
            if file.lower().endswith(".svd") and os.path.splitext(file)[0].lower() == mcu_name_lower:
                svd_file = os.path.join(root_dir, file)
                break
        if svd_file:
            break

    # STM32 family fallback
    if not svd_file:
        family_map = {
            "f030": "STM32F0x0.svd",
            "f031": "STM32F0x1.svd",
            "f042": "STM32F0x2.svd",
            "f051": "STM32F0x1.svd",
            "f072": "STM32F0x2.svd",
        }
        mcu_prefix = mcu_name_lower[5:9] if mcu_name_lower.startswith("stm32") else mcu_name_lower[:4]
        if mcu_prefix in family_map:
            svd_file = os.path.join(svd_root, "stm32", "cortex-m0", family_map[mcu_prefix])

    if not svd_file or not os.path.isfile(svd_file):
        raise FileNotFoundError(f"SVD file for MCU '{mcu_name}' not found in {svd_root}")

    # Parse XML
    tree = ET.parse(svd_file)
    root = tree.getroot()

    # Namespace handling (if any)
    ns = {}
    if root.tag.startswith("{"):
        uri = root.tag.split("}")[0].strip("{")
        ns = {"svd": uri}

    def ns_findtext(elem, path):
        try:
            return elem.findtext(path, namespaces=ns)
        except:
            return elem.findtext(path)

    def ns_findall(elem, path):
        try:
            return elem.findall(path, namespaces=ns)
        except:
            return elem.findall(path)

    def parse_int(text: str | None, default: int = 0) -> int:
        if not text:
            return default
        try:
            return int(text.strip(), 0)
        except ValueError:
            return default

    result = {
        "device": mcu_name_lower,
        "architecture": ns_findtext(root, "cpu/name"),
        "family": ns_findtext(root, "name") or ns_findtext(root, "cpu/name"),
        "peripherals": {},
        "modules": {},
        "memories": {},
        "interrupts": {},
    }

    # -------------------------------
    # 1. Root-level memories (<memory>)
    # -------------------------------
    for mem in ns_findall(root, ".//memory"):
        name = mem.get("name") or mem.findtext("name")
        if not name:
            continue
        start = parse_int(mem.get("start") or mem.findtext("startAddress"))
        size = parse_int(mem.get("size") or mem.findtext("size"))
        mem_type_str = (mem.get("type") or "").lower()
        if not mem_type_str:
            mem_type_str = "flash" if "flash" in name.lower() else "ram"
        result["memories"][name] = {
            "start": start,
            "size": size,
            "type": mem_type_str,
            "pagesize": parse_int(mem.get("pageSize") or mem.findtext("pageSize")),
        }

    # -------------------------------
    # 2. Pre-index peripherals for derivedFrom
    # -------------------------------
    peripheral_elements = {}
    for p in ns_findall(root, ".//peripheral"):
        pname = ns_findtext(p, "name")
        if pname:
            peripheral_elements[pname] = p

    def resolve_peripheral(p_elem):
        derived = p_elem.get("derivedFrom")
        if derived and derived in peripheral_elements:
            return peripheral_elements[derived]
        return p_elem

    # -------------------------------
    # 3. Process each peripheral
    # -------------------------------
    for pname, p_elem in peripheral_elements.items():
        base_elem = resolve_peripheral(p_elem)
        base_addr = parse_int(ns_findtext(p_elem, "baseAddress"))
        caption = ns_findtext(p_elem, "description") or ns_findtext(base_elem, "description") or ""

        # Peripherals
        result["peripherals"][pname] = {"caption": caption, "instances": [{"name": pname}]}

        # Modules
        result["modules"][pname] = {
            "caption": caption,
            "instances": [{"name": pname, "offset": hex(base_addr), "register_group": "REG_GROUP", "address_space": "data"}],
            "register_groups": {"REG_GROUP": {"name_in_module": "REG_GROUP", "caption": caption, "offset": 0, "registers": {}}},
        }

        rg = result["modules"][pname]["register_groups"]["REG_GROUP"]

        # Registers
        for reg in ns_findall(base_elem, "registers/register"):
            reg_name = ns_findtext(reg, "name")
            if not reg_name:
                continue
            reg_offset = parse_int(ns_findtext(reg, "addressOffset"))
            reg_size = parse_int(ns_findtext(reg, "size") or "32")
            reg_rw = ns_findtext(reg, "access") or "read-write"

            # Bitfields
            bitfields = {}
            for bf in ns_findall(reg, "fields/field"):
                bf_name = ns_findtext(bf, "name")
                if not bf_name:
                    continue
                bit_range = ns_findtext(bf, "bitRange")
                if not bit_range:
                    offset = parse_int(ns_findtext(bf, "bitOffset"))
                    width = parse_int(ns_findtext(bf, "bitWidth") or "1")
                    bit_range = f"[{offset+width-1}:{offset}]"
                values = {}
                for val in ns_findall(bf, "enumeratedValues/enumeratedValue"):
                    val_name = ns_findtext(val, "name")
                    if val_name:
                        values[val_name] = {"caption": ns_findtext(val, "description"), "value": ns_findtext(val, "value")}
                bitfields[bf_name] = {"caption": ns_findtext(bf, "description"), "mask": bit_range, "values": values}

            rg["registers"][reg_name] = {
                "caption": ns_findtext(reg, "description"),
                "offset": reg_offset,
                "absolute_address": hex(base_addr + reg_offset),
                "size": reg_size,
                "rw": reg_rw,
                "bitfields": bitfields,
            }

        # Memory blocks (<addressBlock>)
        for addr_block in ns_findall(p_elem, "addressBlock"):
            block_offset = parse_int(ns_findtext(addr_block, "offset"))
            block_size = parse_int(ns_findtext(addr_block, "size"))
            block_usage = (ns_findtext(addr_block, "usage") or "").lower()
            if block_usage in ("ram", "flash", "registers"):
                mem_key = f"{pname}_{block_usage.upper()}"
                result["memories"][mem_key] = {"start": base_addr + block_offset, "size": block_size, "type": block_usage, "pagesize": None}

        # Interrupts inside peripheral
        for intr in ns_findall(p_elem, "interrupt"):
            int_name = ns_findtext(intr, "name")
            if int_name and int_name not in result["interrupts"]:
                result["interrupts"][int_name] = {
                    "index": ns_findtext(intr, "value"),
                    "caption": ns_findtext(intr, "description"),
                    "module_instance": pname,
                }

    # -------------------------------
    # 4. Device-level interrupts
    # -------------------------------
    for intr in ns_findall(root, ".//interrupts/interrupt"):
        int_name = ns_findtext(intr, "name")
        if int_name and int_name not in result["interrupts"]:
            result["interrupts"][int_name] = {
                "index": ns_findtext(intr, "value"),
                "caption": ns_findtext(intr, "description"),
                "module_instance": None,
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
        return load_svd_for_mcu(mcu_name, svd_root="mcu_db")
    else:
        raise ValueError(f"Unsupported MCU platform: {platform}")

