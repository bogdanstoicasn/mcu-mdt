import yaml
import os
import xml.etree.ElementTree as ET
from pc_tool.common.logger import MDTLogger
from pc_tool.common.enums import MCUPlatforms

class ConfigLoader:
    def __init__(
        self,
        build_info_path: str,
        commands_path: str = "pc_tool/configs/commands.yaml",
        platforms_path: str = "pc_tool/configs/platforms",
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
    STM32_FLASH_BASE = 0x08000000
    STM32_RAM_BASE   = 0x20000000

    mcu_name_lower = mcu_name.lower()

    if not mcu_name_lower.startswith("stm32"):
        mcu_name_lower = "stm32" + mcu_name_lower

    svd_file = None

    # SVD location
    for root_dir, _, files in os.walk(svd_root):
        for file in files:
            if file.lower().endswith(".svd") and os.path.splitext(file)[0].lower() == mcu_name_lower:
                svd_file = os.path.join(root_dir, file)
                break
        if svd_file:
            break

    # Family fallback: maps 4-char prefix  (core subfolder, shared SVD filename)
    if not svd_file:
        family_map = {
            "f030": ("cortex-m0", "STM32F0x0.svd"),
            "f031": ("cortex-m0", "STM32F0x1.svd"),
            "f042": ("cortex-m0", "STM32F0x2.svd"),
            "f051": ("cortex-m0", "STM32F0x1.svd"),
            "f072": ("cortex-m0", "STM32F0x2.svd"),
            "f103": ("cortex-m3", "STM32F103.svd"),
        }
        mcu_prefix = mcu_name_lower[5:9]
        if mcu_prefix in family_map:
            subfolder, svd_filename = family_map[mcu_prefix]
            svd_file = os.path.join(svd_root, "stm32", subfolder, svd_filename)

    if not svd_file or not os.path.isfile(svd_file):
        raise FileNotFoundError(f"SVD file for MCU '{mcu_name}' not found in {svd_root}")

    # Companion YAML for memory sizes
    yaml_file = os.path.splitext(svd_file)[0] + ".yaml"
    mcu_memory_data = None
    if os.path.isfile(yaml_file):
        mcu_memory_data = load_configs(yaml_file)

    # Parse XML
    try:
        tree = ET.parse(svd_file)
        root = tree.getroot()
    except ET.ParseError as e:
        raise ValueError(f"Invalid SVD XML: {e}")

    # Handle namespaces if present
    ns = {}
    if root.tag.startswith("{"):
        uri = root.tag.split("}")[0].strip("{")
        ns = {"svd": uri}

    def _findtext(elem: ET.Element, path: str) -> str | None:
        try:
            return elem.findtext(path, namespaces=ns)
        except TypeError:
            return elem.findtext(path)

    def _findall(elem: ET.Element, path: str) -> list[ET.Element]:
        try:
            return elem.findall(path, namespaces=ns)
        except TypeError:
            return elem.findall(path)

    def _parse_int(text: str | None, default: int = 0) -> int:
        if not text:
            return default
        try:
            return int(text.strip(), 0)
        except ValueError:
            return default

    # Basic device info
    result = {
        "device":       mcu_name_lower,
        "architecture": _findtext(root, "cpu/name"),
        "family":       _findtext(root, "name"),
        "peripherals":  {},
        "modules":      {},
        "memories":     {},
        "interrupts":   {},
    }

    # Memory info from companion YAML (if available)
    if mcu_memory_data:
        variants = mcu_memory_data.get("variants", {})
        variant  = variants.get(mcu_name_lower, {})

        flash_size = variant.get("flash")
        ram_size   = variant.get("ram")
        flash_page = variant.get("flash_page")

        if flash_size:
            result["memories"]["FLASH"] = {
                "start":    STM32_FLASH_BASE,
                "size":     flash_size,
                "type":     "flash",
                "pagesize": str(flash_page) if flash_page else None,
            }

        if ram_size:
            result["memories"]["RAM"] = {
                "start":    STM32_RAM_BASE,
                "size":     ram_size,
                "type":     "ram",
                "pagesize": None,
            }

    # Pre-index peripherals for derivedFrom resolution
    peripheral_elements: dict[str, ET.Element] = {}
    for p in _findall(root, ".//peripheral"):
        pname = _findtext(p, "name")
        if pname:
            peripheral_elements[pname] = p

    def _resolve(p_elem: ET.Element) -> ET.Element:
        derived = p_elem.get("derivedFrom")
        if derived and derived in peripheral_elements:
            return peripheral_elements[derived]
        return p_elem

    # Parse peripherals and their registers
    for pname, p_elem in peripheral_elements.items():
        base_elem = _resolve(p_elem)
        base_addr = _parse_int(_findtext(p_elem, "baseAddress"))
        caption   = _findtext(p_elem, "description") or _findtext(base_elem, "description") or ""

        result["peripherals"][pname] = {
            "caption":   caption,
            "instances": [{"name": pname}],
        }

        result["modules"][pname] = {
            "caption":         caption,
            "instances":       [
                {
                    "name":           pname,
                    "offset":         hex(base_addr),
                    "register_group": pname,
                    "address_space":  "data",
                }
            ],
            "register_groups": {},
        }

        result["modules"][pname]["register_groups"][pname] = {
            "name_in_module": pname,
            "caption":        caption,
            "offset":         hex(base_addr),
            "registers":      {},
        }

        rg = result["modules"][pname]["register_groups"][pname]

        for reg in _findall(base_elem, "registers/register"):
            reg_name = _findtext(reg, "name")
            if not reg_name:
                continue

            reg_offset = _parse_int(_findtext(reg, "addressOffset"))
            reg_size   = _parse_int(_findtext(reg, "size") or "32", default=32)
            reg_rw     = _findtext(reg, "access") or "read-write"
            reg_mask   = _findtext(reg, "resetMask") or None

            bitfields: dict = {}
            for bf in _findall(reg, "fields/field"):
                bf_name = _findtext(bf, "name")
                if not bf_name:
                    continue

                bit_range = _findtext(bf, "bitRange")
                if not bit_range:
                    lsb       = _parse_int(_findtext(bf, "bitOffset"))
                    width     = _parse_int(_findtext(bf, "bitWidth") or "1", default=1)
                    bit_range = f"[{lsb + width - 1}:{lsb}]"

                values: dict = {}
                for val in _findall(bf, "enumeratedValues/enumeratedValue"):
                    val_name = _findtext(val, "name")
                    if val_name:
                        values[val_name] = {
                            "caption": _findtext(val, "description"),
                            "value":   _findtext(val, "value"),
                        }

                bitfields[bf_name] = {
                    "caption": _findtext(bf, "description"),
                    "mask":    bit_range,
                    "values":  values,
                }

            rg["registers"][reg_name] = {
                "caption":   _findtext(reg, "description"),
                "offset":    str(reg_offset),
                "size":      str(reg_size),
                "mask":      reg_mask,
                "rw":        reg_rw,
                "bitfields": bitfields,
            }

        for intr in _findall(p_elem, "interrupt"):
            int_name = _findtext(intr, "name")
            if int_name and int_name not in result["interrupts"]:
                result["interrupts"][int_name] = {
                    "index":           _findtext(intr, "value"),
                    "caption":         _findtext(intr, "description"),
                    "module_instance": pname,
                }

    # Interrupt blocks
    for intr in _findall(root, ".//interrupts/interrupt"):
        int_name = _findtext(intr, "name")
        if int_name and int_name not in result["interrupts"]:
            result["interrupts"][int_name] = {
                "index":           _findtext(intr, "value"),
                "caption":         _findtext(intr, "description"),
                "module_instance": None,
            }

    return result

def load_mcu_metadata(mcu_name: str, mcu_platform: str) -> dict:

    platform = mcu_platform.lower()

    if platform == MCUPlatforms.AVR:
        return load_atdf_for_mcu(mcu_name, atdf_root="pc_tool/mcu_db")
    elif platform == MCUPlatforms.PIC:
        # Placeholder for PIC metadata loading logic
        raise NotImplementedError("PIC platform support not implemented yet")
    elif platform == MCUPlatforms.STM:
        return load_svd_for_mcu(mcu_name, svd_root="pc_tool/mcu_db")
    else:
        raise ValueError(f"Unsupported MCU platform: {platform}")
